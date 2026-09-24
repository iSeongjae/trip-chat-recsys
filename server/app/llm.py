"""발화 → 턴 JSON (LLM 파서). 추천할 장소는 LLM 이 정하지 않는다: LLM 은 조건만 뽑고, 장소는 서버(japan_rec)가 고른다.
reply 는 장소 이름 없이 받아주는 한 문장. OPENAI_API_KEY 가 없으면 키워드 규칙으로 대신한다(개발용)."""
import json, re, time, hashlib
from . import config

CATS = ['meal', 'cafe', 'bar', 'sight', 'walk', 'shop', 'rest', 'none']
THEMES = ['none', 'famous', 'local', 'known', 'hidden', 'season']
SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'reply': {'type': 'string'},
        'next_category': {'type': 'string', 'enum': CATS},
        'include_sub': {'type': 'array', 'items': {'type': 'string'}},
        'exclude_sub': {'type': 'array', 'items': {'type': 'string'}},
        'include_brand': {'type': 'array', 'items': {'type': 'string'}},
        'max_distance_km': {'type': ['number', 'null']},
        'local': {'type': ['boolean', 'null']},
        'theme': {'type': 'string', 'enum': THEMES},
        'month': {'type': ['integer', 'null']},
        'location_query': {'type': ['string', 'null']},
        'visited_mention': {'type': 'array', 'items': {'type': 'string'}},
        'stable_local': {'type': ['boolean', 'null']},
        'stable_max_distance_km': {'type': ['number', 'null']},
    },
}
SCHEMA['required'] = list(SCHEMA['properties'])

PROMPT = '''너는 일본 여행 추천 앱 "이제 뭐 하지?"의 대화 파서다. 한국인 여행자의 **마지막 메시지**를 JSON 으로 바꾼다.
장소는 서버가 고른다. 너는 절대 가게·명소 이름이나 사실(영업시간, 가격, 맛)을 지어내지 않는다.
이전 대화는 "이거", "거기" 같은 말을 이해할 때만 참고한다. 이전에 말한 종류·조건을 이번 JSON 에 옮기지 않는다.
사용자가 **이번에 직접 말한 것만** 채운다. 말하지 않은 값은 비워 둔다([], null, none).

- next_category: 다음에 할 것. meal(식사) cafe(카페·디저트·빵) bar(술·이자카야) sight(구경: 신사·절·박물관·성·전망대) walk(산책·자연·공원) shop(쇼핑) rest(휴식: 온천·사우나). 모르겠으면 none.
- include_sub: 사용자가 이번에 콕 집은 음식·장소 종류만 **한국어로** 짧게 ("라멘", "우동", "야키토리", "일식", "신사", "공원", "그리스 요리"). "밥", "먹을 거", "산책", "구경" 같은 일반적인 말은 넣지 않는다. 없으면 [].
- exclude_sub: "~말고" 할 때 그 종류 이름만 ("라멘 말고 우동" → exclude ["라멘"], include ["우동"]). "말고"라는 단어 자체는 넣지 않는다. include_brand: 브랜드("돈키호테" → "ドン・キホーテ", "스타벅스" → "スターバックス").
- max_distance_km: 거리를 말했을 때만 ("걸어서 5분" → 0.4, "가까운" → 0.5, "좀 멀어도" → 3). 아니면 null.
- local: "현지인", "로컬"이라고 말했을 때만 true, "유명한 곳"이라고 말했을 때만 false. 그 외에는 null.
- theme: 관광지를 이렇게 말할 때만: 유명 명소 famous, 현지인 인기 명소 local, 한국인 인기 명소 known, 숨은 명소·외국인 명소 hidden, 이번 달·요즘 명소 season. 음식은 theme 을 쓰지 않는다. 아니면 none.
- month: theme 이 season 이고 사용자가 달을 말했을 때만 1~12 ("10월 명소" → 10, "다음 달" → 오늘 기준 다음 달). 아니면 null.
- location_query: 지금 있는 곳을 말하면 그 이름 ("교토역에 있어" → "교토역"). 아니면 null.
- visited_mention: 이미 다녀왔다고 말한 장소 이름들.
- stable_local / stable_max_distance_km: "나는 원래 ~ 좋아해"처럼 지속 성향일 때만.
- reply: 한국어 **짧은 한 문장**(30자 안팎), 친근하게. 장소 이름·영어 코드(meal, season 등)·질문은 쓰지 않는다.
  예: "혼밥 라멘 좋죠! 근처로 골라봤어요." / "우동으로 바꿔볼게요." / "배부르니 산책 좋죠!"
  next_category 도 theme 도 없으면 그때만 무엇을 하고 싶은지 짧게 묻는다 ("뭐 하고 싶으세요? 먹을 것, 구경, 산책 중에 골라주세요").'''


def prompt_version():
    return hashlib.sha256((PROMPT + json.dumps(SCHEMA, sort_keys=True)).encode()).hexdigest()[:10]


def _client():
    from openai import OpenAI
    return OpenAI(api_key=config.OPENAI_API_KEY, timeout=30)


def parse(message, history=(), use_llm=True):
    """history: 최근 대화 [(role, text)] 몇 개 (맥락용). use_llm=False: 서비스 전체 하루 한도를 넘어 규칙 파서로."""
    if config.LLM_MOCK:
        import random
        time.sleep(random.uniform(1.5, 2.5))   # 실제 gpt-5-mini 응답 시간 흉내
        return dict(fallback(message), _meta={'status': 'mock', 'model': 'mock', 'prompt_version': prompt_version()})
    if not config.OPENAI_API_KEY or not use_llm:
        return dict(fallback(message), _meta={'status': 'mock' if use_llm else 'budget', 'model': 'rules', 'prompt_version': prompt_version()})
    t0 = time.time()
    import datetime
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()
    msgs = [{'role': 'system', 'content': PROMPT}, {'role': 'system', 'content': f'오늘(일본 시간): {today.isoformat()}'}]
    for role, text in list(history)[-6:]:
        msgs.append({'role': 'user' if role == 'user' else 'assistant', 'content': text})
    msgs.append({'role': 'user', 'content': message})
    try:
        r = _client().chat.completions.create(
            model=config.OPENAI_MODEL, messages=msgs, reasoning_effort='minimal',
            response_format={'type': 'json_schema', 'json_schema': {'name': 'turn', 'strict': True, 'schema': SCHEMA}})
        out = json.loads(r.choices[0].message.content)
    except Exception as ex:   # 크레딧 소진(insufficient_quota)·장애·시간 초과 → 규칙 파서로 (대화는 계속)
        err = getattr(ex, 'code', None) or type(ex).__name__
        return dict(fallback(message), _meta={'status': 'error', 'error': str(err)[:60], 'model': 'rules', 'prompt_version': prompt_version(),
                                               'latency_ms': round((time.time() - t0) * 1000)})
    u = r.usage.model_dump() if r.usage else {}
    out['_usage'] = u
    out['_meta'] = {'status': 'ok', 'model': config.OPENAI_MODEL, 'prompt_version': prompt_version(), 'latency_ms': round((time.time() - t0) * 1000),
                    'input_tokens': u.get('prompt_tokens'), 'cached_tokens': (u.get('prompt_tokens_details') or {}).get('cached_tokens'),
                    'output_tokens': u.get('completion_tokens'), 'reasoning_tokens': (u.get('completion_tokens_details') or {}).get('reasoning_tokens')}
    return out


KW = [('meal', '밥|먹|식사|점심|저녁|아침|라멘|우동|소바|스시|초밥|고기|야키|카레|돈카츠'), ('cafe', '카페|커피|디저트|빵|케이크'),
      ('bar', '술|이자카야|맥주|바\\b|한잔'), ('sight', '구경|신사|절|사찰|박물관|미술관|성\\b|전망'), ('walk', '산책|공원|자연|정원|산\\b|바다'),
      ('shop', '쇼핑|돈키|드럭|기념품|쇼핑몰'), ('rest', '온천|사우나|쉬')]


def fallback(message):
    cat = next((c for c, rx in KW if re.search(rx, message)), 'none')
    return {'reply': '좋아요, 근처로 골라볼게요.' if cat != 'none' else '뭐 하고 싶으세요? 먹을 것, 구경, 산책, 쇼핑 중에 골라주세요.',
            'next_category': cat, 'include_sub': [], 'exclude_sub': [], 'include_brand': [], 'max_distance_km': None, 'local': None,
            'theme': 'none', 'month': None, 'location_query': None, 'visited_mention': [], 'stable_local': None, 'stable_max_distance_km': None}

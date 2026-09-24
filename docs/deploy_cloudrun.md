# Google Cloud Run 배포 (web + api, 도쿄) — DB 는 Supabase

```
사용자 ─ https ─ wsid-web (nginx: 화면, /api·/auth 는 api 로 전달) ─ wsid-api (FastAPI + 장소 데이터) ─ Supabase(도쿄)
```
파일: `deploy/cloudrun/` (Dockerfile.api, Dockerfile.web, nginx.conf.template, cloudbuild.yaml), 루트 `.gcloudignore`

## 0. 한 번만: 준비
```bash
brew install --cask google-cloud-sdk
gcloud auth login
gcloud config set project <프로젝트ID>
gcloud config set run/region asia-northeast1
PROJECT=$(gcloud config get-value project); REGION=asia-northeast1; REPO=$REGION-docker.pkg.dev/$PROJECT/wsid

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
gcloud artifacts repositories create wsid --repository-format=docker --location=$REGION
```

## 1. 비밀값 (Secret Manager) — 키를 이미지·명령 기록에 남기지 않음
```bash
set -a; . ./.env; set +a                        # 로컬 .env 에서 읽음
printf %s "$OPENAI_API_KEY"        | gcloud secrets create openai-api-key --data-file=-
printf %s "$SUPABASE_DB_PASSWORD"  | gcloud secrets create supabase-db-password --data-file=-
python3 -c "import secrets;print(secrets.token_hex(32),end='')" | gcloud secrets create session-secret --data-file=-
python3 -c "import secrets;print(secrets.token_hex(32),end='')" | gcloud secrets create proxy-secret --data-file=-   # web→api 확인용
SA=$(gcloud projects describe $PROJECT --format='value(projectNumber)')-compute@developer.gserviceaccount.com
for s in openai-api-key supabase-db-password session-secret proxy-secret; do
  gcloud secrets add-iam-policy-binding $s --member=serviceAccount:$SA --role=roles/secretmanager.secretAccessor
done
```

## 2. 이미지 빌드 (Cloud Build, 로컬 Docker 불필요, 약 5분)
```bash
TAG=v1
gcloud builds submit --config deploy/cloudrun/cloudbuild.yaml --substitutions _REPO=$REPO,_TAG=$TAG
```

## 3. api 배포
```bash
gcloud run deploy wsid-api --image $REPO/api:$TAG \
  --memory 3Gi --cpu 2 --min-instances 1 --max-instances 3 --concurrency 40 --timeout 60 --cpu-boost \
  --allow-unauthenticated \
  --set-env-vars APP_ENV=prod,OPENAI_MODEL=gpt-5-mini,DAILY_CHAT_LIMIT=100,SUPABASE_DB_HOST=$SUPABASE_DB_HOST,SUPABASE_DB_PORT=$SUPABASE_DB_PORT,SUPABASE_DB_NAME=$SUPABASE_DB_NAME,SUPABASE_DB_USER=$SUPABASE_DB_USER \
  --set-secrets OPENAI_API_KEY=openai-api-key:latest,SUPABASE_DB_PASSWORD=supabase-db-password:latest,SESSION_SECRET=session-secret:latest,PROXY_SECRET=proxy-secret:latest
API_URL=$(gcloud run services describe wsid-api --format='value(status.url)')
curl -s -o /dev/null -w '%{http_code}\n' $API_URL/health   # 403: api 는 web(nginx)을 거친 요청만 받음 (아래 '보안')
```
- min-instances 1: 켤 때 장소 데이터(114MB)를 메모리에 올리는 데 몇 초 걸려서, 첫 사용자가 기다리지 않게 1개는 항상 켜 둠
- 메모리 3Gi: 데이터 약 1.6GB + 여유

## 4. web 배포
```bash
gcloud run deploy wsid-web --image $REPO/web:$TAG \
  --memory 256Mi --cpu 1 --min-instances 0 --max-instances 3 --allow-unauthenticated \
  --set-env-vars API_URL=$API_URL,API_HOST=${API_URL#https://} --set-secrets PROXY_SECRET=proxy-secret:latest
WEB_URL=$(gcloud run services describe wsid-web --format='value(status.url)')
gcloud run services update wsid-api --update-env-vars BASE_URL=$WEB_URL      # 쿠키 secure·구글 콜백 기준
echo $WEB_URL                                    # 이 주소로 접속
curl -s $WEB_URL/health                          # {"ok":true,"items":372304,...}
```

## 5. (선택) 내 도메인
```bash
gcloud beta run domain-mappings create --service wsid-web --domain <도메인> --region $REGION
# 안내되는 DNS 레코드를 도메인 관리 화면에 추가 → 인증서 자동 발급 (수십 분)
gcloud run services update wsid-api --update-env-vars BASE_URL=https://<도메인>
```
리전에서 도메인 매핑이 안 되면 Cloudflare(프록시) 또는 외부 HTTPS 로드밸런서로 연결.

## 업데이트
```bash
TAG=v2
gcloud builds submit --config deploy/cloudrun/cloudbuild.yaml --substitutions _REPO=$REPO,_TAG=$TAG
gcloud run deploy wsid-web --image $REPO/web:$TAG    # web 먼저: 새 헤더를 붙이는 쪽이 먼저 떠 있어야 끊김 없음
gcloud run deploy wsid-api --image $REPO/api:$TAG
```
DB 스키마가 바뀌었으면 배포 전에 `python3 scripts/db/migrate.py` (컬럼 추가처럼 예전 코드와 함께 돌아가는 변경만).
되돌리기: Cloud Run 콘솔 → 서비스 → 버전(Revisions)에서 이전 버전으로 트래픽 100%

## 확인
- `$WEB_URL/health`, 게스트로 대화 → Supabase `turn_logs` 에 한 줄 (`context.country` 에 KR 등)
- 로그: `gcloud run services logs read wsid-api --limit 50`

## 보안
- **api 직접 호출 차단**: api(run.app 주소)는 공개 주소지만, nginx 가 붙이는 `X-Proxy-Secret`(Secret Manager `proxy-secret`)이 맞는 요청만 받는다(`server/app/security.py`). 그래서 요청 크기 제한(64KB)·사용자 IP 를 nginx 한 곳에서 정한다.
- **사용자 IP**: nginx 가 `X-Forwarded-For` 의 맨 끝 값(Cloud Run 앞단이 붙인 실제 접속 IP)만 `X-Client-IP` 로 넘긴다. 국가 로그와 요청 제한에 쓰고 DB 에는 저장하지 않는다.
- **남용·비용 제한** (환경변수, 기본값):

  | 변수 | 기본 | 내용 |
  |---|---|---|
  | `DAILY_CHAT_LIMIT` | 100 | 사용자별 하루 대화 수 (넘으면 429) |
  | `LLM_DAILY_LIMIT` | 2000 | 서비스 전체 하루 LLM 호출 수. 넘으면 규칙 파서로 대신 (turn_logs.llm.status = `budget`) |
  | `GUEST_PER_IP_DAILY` | 30 | IP 하나가 하루에 만들 수 있는 게스트 수 |
  | `RATE_PER_MIN` | 30 | IP 별 1분 요청 수 (대화·칩·구글 로그인) |

  요청 제한은 인스턴스 메모리에서 세므로 인스턴스가 여러 개면 그 수만큼 느슨해진다 (최대 3). OpenAI 쪽에도 프로젝트 월 예산 한도를 걸어 둔다.
- **로그아웃**: 쿠키는 서명한 `[uid, session_ver]`. 로그아웃하면 `users.session_ver` 가 올라가 그 계정의 예전 쿠키가 모두 무효.
- **헤더**: nginx 가 HSTS·X-Frame-Options·X-Content-Type-Options·Referrer-Policy·CSP(frame-ancestors 등)를 붙이고(`deploy/cloudrun/security_headers.conf`), API 응답은 `Cache-Control: no-store`.
- **컨테이너**: api 는 uid 10001, web 은 `nginx-unprivileged`(uid 101)로 실행.

## 의존성 고정
api 이미지는 `server/requirements.lock`(전체 버전 고정)을 설치한다. `server/requirements.txt` 를 바꾸면 다시 만든다:
```bash
pip install -q --dry-run --ignore-installed --only-binary=:all: --python-version 3.12 --implementation cp \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
  --target /tmp/lock --report /tmp/lock.json -r server/requirements.txt
python3 -c "import json;r=json.load(open('/tmp/lock.json'));print('\n'.join(sorted(f\"{i['metadata']['name'].lower()}=={i['metadata']['version']}\" for i in r['install'])))"
```
위 출력을 `server/requirements.lock` 의 주석 두 줄 아래에 넣는다.

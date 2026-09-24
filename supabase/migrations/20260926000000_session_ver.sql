-- 로그아웃하면 그 계정의 기존 쿠키를 모두 무효로 (쿠키 = 서명한 [uid, session_ver], server/app/auth.py)
alter table users add column if not exists session_ver int not null default 0;

-- 서비스 전체 하루 LLM 호출 수 (LLM_DAILY_LIMIT) 를 셀 때 쓰는 인덱스
create index if not exists usage_daily_day on usage_daily(day);

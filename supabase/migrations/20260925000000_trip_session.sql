-- 서버의 세션 상태(japan_rec.profile 의 session: 현재 위치·동행·대기 근거 등)를 통째로 저장하는 칸.
-- GPS 로 정한 현재 위치는 서버가 소수 2자리(약 1km)로 반올림해 넣는다. 역·공항·장소를 고른 경우는 그 장소 좌표.
alter table trip_state add column session jsonb not null default '{}';

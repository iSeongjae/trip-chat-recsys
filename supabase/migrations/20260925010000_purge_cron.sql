-- 게스트 30일 만료 처리를 DB 가 매일 직접 실행 (서버는 요청 기반 결제라 요청 밖에서 CPU 가 멈춤).
-- 매일 19:00 UTC = 04:00 KST
create extension if not exists pg_cron with schema pg_catalog;
do $$
begin
  if exists (select 1 from cron.job where jobname = 'purge-expired') then
    perform cron.unschedule('purge-expired');
  end if;
  perform cron.schedule('purge-expired', '0 19 * * *', 'select public.purge_expired()');
end $$;

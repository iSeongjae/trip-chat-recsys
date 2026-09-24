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
SA=$(gcloud projects describe $PROJECT --format='value(projectNumber)')-compute@developer.gserviceaccount.com
for s in openai-api-key supabase-db-password session-secret; do
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
  --set-secrets OPENAI_API_KEY=openai-api-key:latest,SUPABASE_DB_PASSWORD=supabase-db-password:latest,SESSION_SECRET=session-secret:latest
API_URL=$(gcloud run services describe wsid-api --format='value(status.url)')
curl -s $API_URL/health                          # {"ok":true,"items":372325,...}
```
- min-instances 1: 켤 때 장소 데이터(114MB)를 메모리에 올리는 데 몇 초 걸려서, 첫 사용자가 기다리지 않게 1개는 항상 켜 둠
- 메모리 3Gi: 데이터 약 1.6GB + 여유

## 4. web 배포
```bash
gcloud run deploy wsid-web --image $REPO/web:$TAG \
  --memory 256Mi --cpu 1 --min-instances 0 --max-instances 3 --allow-unauthenticated \
  --set-env-vars API_URL=$API_URL,API_HOST=${API_URL#https://}
WEB_URL=$(gcloud run services describe wsid-web --format='value(status.url)')
gcloud run services update wsid-api --update-env-vars BASE_URL=$WEB_URL      # 쿠키 secure·구글 콜백 기준
echo $WEB_URL                                    # 이 주소로 접속
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
gcloud run deploy wsid-api --image $REPO/api:$TAG
gcloud run deploy wsid-web --image $REPO/web:$TAG
```
되돌리기: Cloud Run 콘솔 → 서비스 → 버전(Revisions)에서 이전 버전으로 트래픽 100%

## 확인
- `$WEB_URL/health`, 게스트로 대화 → Supabase `turn_logs` 에 한 줄 (`context.country` 에 KR 등)
- 로그: `gcloud run services logs read wsid-api --limit 50`

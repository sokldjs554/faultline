#!/usr/bin/env bash
# Azure Container Apps 에 배포한다. 이미지는 로컬 Docker 없이 Azure Container Registry 에서 빌드한다.
#
# 준비: Azure CLI 설치 후 `az login`, 구독이 여러 개면 `az account set -s <구독>`.
# 사용: LOCATION=koreacentral deploy/azure/containerapp.sh
# 첫 실행은 리소스 그룹, 레지스트리, 환경, 앱을 모두 만든다. 다시 실행하면 새 이미지로 앱을 갱신한다.
# 정리: az group delete -n faultline-rg --yes   (만든 리소스를 한 번에 지운다)
set -euo pipefail
cd "$(dirname "$0")/../.."

LOCATION="${LOCATION:-koreacentral}"
RG="${RG:-faultline-rg}"
APP="${APP:-faultline}"

az extension add --name containerapp --upgrade --only-show-errors
az provider register --namespace Microsoft.App --wait >/dev/null
az provider register --namespace Microsoft.OperationalInsights --wait >/dev/null

# --source 는 Dockerfile 이 있는 폴더를 ACR 에서 빌드해 앱을 만든다. 서버 포트는 Dockerfile 의 8000 이다.
az containerapp up \
  --name "$APP" --resource-group "$RG" --location "$LOCATION" \
  --source . --ingress external --target-port 8000 \
  --env-vars FAULTLINE_ARTIFACT_DIR=/app/artifacts

# 정의 평가는 데모 세계를 만들어 메모리를 쓰므로 자원을 늘린다. 비용을 줄이려면 최소 복제본을 0 으로 둔다(첫 요청이 느려진다).
az containerapp update --name "$APP" --resource-group "$RG" \
  --cpu 1 --memory 2Gi --min-replicas 0 --max-replicas 2

FQDN="$(az containerapp show --name "$APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
echo "배포 주소: https://$FQDN/console/"
for i in 1 2 3 4 5 6; do
  if curl -fsS "https://$FQDN/health" >/dev/null; then echo "헬스체크 통과"; exit 0; fi
  sleep 10
done
echo "헬스체크가 통과하지 않았다. az containerapp logs show -n $APP -g $RG --follow 로 확인한다" >&2
exit 1

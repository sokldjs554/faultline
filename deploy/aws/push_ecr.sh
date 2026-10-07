#!/usr/bin/env bash
# 사용: AWS_REGION=ap-northeast-2 deploy/aws/push_ecr.sh
set -euo pipefail
REGION="${AWS_REGION:-ap-northeast-2}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REPO="faultline"
aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 || aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
docker build -t "$REPO:latest" .
docker tag "$REPO:latest" "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"
docker push "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"
echo "pushed: $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest — App Runner 서비스의 소스로 지정하세요 (포트 8000, 헬스체크 /health)"

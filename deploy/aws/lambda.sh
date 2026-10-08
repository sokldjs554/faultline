#!/usr/bin/env bash
# AWS Lambda(컨테이너 이미지) + 함수 URL 로 배포한다. 이 방식은 Lambda 의 월 무료 한도 안에서 돌아간다.
# (App Runner 는 2026년 4월 30일부터 신규 고객을 받지 않아 쓰지 않는다.)
#
# 준비: Docker, AWS CLI v2, `aws configure`(루트 키가 아닌 IAM 사용자 또는 SSO).
#       그 사용자는 ECR, Lambda, IAM 역할을 만들 수 있어야 한다(처음 한 번은 AdministratorAccess 가 가장 쉽다).
# 사용: AWS_REGION=ap-northeast-2 deploy/aws/lambda.sh
# 다시 실행하면 새 이미지로 함수를 갱신한다.
# 정리: aws lambda delete-function-url-config --function-name faultline
#       aws lambda delete-function --function-name faultline
#       aws ecr delete-repository --repository-name faultline --force
#       aws iam detach-role-policy --role-name faultline-lambda-role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
#       aws iam delete-role --role-name faultline-lambda-role
set -euo pipefail
cd "$(dirname "$0")/../.."

REGION="${AWS_REGION:-ap-northeast-2}"
FN="${FN:-faultline}"
REPO="${REPO:-faultline}"
ROLE_NAME="${ROLE_NAME:-faultline-lambda-role}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
IMAGE="$REGISTRY/$REPO:latest"

# 1. 이미지를 ECR 에 올린다. Lambda 는 단일 플랫폼 이미지만 받으므로 amd64 로 고정하고 provenance 를 끈다.
aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker build --platform linux/amd64 --provenance=false -f Dockerfile.lambda -t "$IMAGE" .
docker push "$IMAGE"

# 2. 실행 역할(로그만 쓸 수 있다)
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE_NAME" >/dev/null \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  sleep 15  # 역할이 퍼질 때까지 기다린다
fi
ROLE_ARN="$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text)"

# 3. 함수와 함수 URL
if aws lambda get-function --function-name "$FN" --region "$REGION" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FN" --image-uri "$IMAGE" --region "$REGION" >/dev/null
  aws lambda wait function-updated-v2 --function-name "$FN" --region "$REGION"
else
  aws lambda create-function --function-name "$FN" --region "$REGION" \
    --package-type Image --code "ImageUri=$IMAGE" --role "$ROLE_ARN" --architectures x86_64 \
    --memory-size 2048 --timeout 120 \
    --environment "Variables={FAULTLINE_ARTIFACT_DIR=/app/artifacts}" >/dev/null
  aws lambda wait function-active-v2 --function-name "$FN" --region "$REGION"
  aws lambda create-function-url-config --function-name "$FN" --region "$REGION" --auth-type NONE >/dev/null
  # 인증 없는 함수 URL 은 두 권한이 모두 있어야 403 이 나지 않는다
  aws lambda add-permission --function-name "$FN" --region "$REGION" --statement-id UrlInvokeUrl \
    --action lambda:InvokeFunctionUrl --principal "*" --function-url-auth-type NONE >/dev/null
  aws lambda add-permission --function-name "$FN" --region "$REGION" --statement-id UrlInvokeFunction \
    --action lambda:InvokeFunction --principal "*" --invoked-via-function-url >/dev/null
fi

URL="$(aws lambda get-function-url-config --function-name "$FN" --region "$REGION" --query FunctionUrl --output text)"
echo "배포 주소: ${URL}console/"
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do  # 첫 요청은 이미지를 불러오느라 느리다
  if curl -fsS --max-time 30 "${URL}health" >/dev/null; then echo "헬스체크 통과"; exit 0; fi
  sleep 10
done
echo "헬스체크가 통과하지 않았다. CloudWatch 로그(/aws/lambda/$FN)를 확인한다" >&2
exit 1

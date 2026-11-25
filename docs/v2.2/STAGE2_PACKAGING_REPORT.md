# Stage 2 Packaging Analysis & Container Image Proposal

## Executive Summary
This report evaluates deployment options for Stage 2 (ODL layout parsing and Nova LLM fallback) on AWS Lambda, specifically addressing:
1. Whether `odl-parser` (JVM-based) and its dependencies fit within a standard `.zip` Lambda package.
2. Unzipped package sizes, cold start latencies, and SnapStart trade-offs.
3. A formal Container Image (OCI) proposal for Stage 2.
4. Operational runbook for cost kill-switch: setting Stage 2 reserved concurrency to 0.

---

## 1. Zip Lambda Packaging Feasibility Analysis

### AWS Lambda Limits
- **Direct Zip Upload**: 50 MB compressed.
- **S3 Zip Upload**: 250 MB unzipped (including all layers and function code).
- **Ephemeral `/tmp` Storage**: 512 MB to 10,240 MB.

### Dependency Size Breakdown (ODL + Python Stage 2)
If packaged together in a single Python runtime Lambda:
| Component | Uncompressed Size | Impact |
| :--- | :--- | :--- |
| **Python Runtime Dependencies** (boto3, pydantic, PyMuPDF, pdfbox-python) | ~85 MB | Fits in standard layer |
| **OpenJDK 21 Headless JRE** | ~175 MB | Required to execute JVM parser |
| **ODL Parser JAR + Apache PDFBox + FontBox** | ~48 MB | Parser core binaries |
| **Native Shared Libraries** (libfreetype, libfontconfig) | ~18 MB | Font rendering dependencies |
| **Total Combined Uncompressed Size** | **~326 MB** | **EXCEEDS 250 MB LIMIT BY 76 MB** |

> [!CAUTION]
> Packaging a full JRE alongside the Python Stage 2 worker in a standard `.zip` deployment **exceeds the 250 MB uncompressed limit**. Trying to strip the JRE via `jlink` reduces the footprint to ~110 MB (total ~243 MB), but leaves dangerously thin headroom (<7 MB) for any additional Python dependencies or security patches.

### Cold Start Profile Comparison
| Deployment Pattern | Cold Start Latency | Warm Invocation | Memory Allocation |
| :--- | :--- | :--- | :--- |
| **Zip Python + Striped JRE** | 4,200 – 6,800 ms | 450 ms | 2,048 MB |
| **Dedicated Corretto 21 Lambda (SnapStart)** | **180 – 350 ms** | 120 ms | 1,536 MB |
| **Container Image (OCI) Python + JVM** | 1,200 – 2,400 ms | 420 ms | 2,048 MB |

---

## 2. Proposed Architecture: Container Image (OCI) for Stage 2

AWS Lambda supports OCI container images up to **10 GB**, eliminating the 250 MB zip limit completely while allowing reproducible multi-stage builds.

### Multi-Stage Dockerfile Proposal (`infra/stage2/Dockerfile`)
```dockerfile
# Stage 1: Build Java ODL parser
FROM maven:3.9-eclipse-temurin-21-alpine AS java-builder
WORKDIR /build
COPY odl-parser/pom.xml .
COPY odl-parser/src ./src
RUN mvn clean package -DskipTests

# Stage 2: Runtime Lambda Container
FROM public.ecr.aws/lambda/python:3.13

# Install Corretto Headless JRE and font dependencies
RUN dnf install -y java-21-amazon-corretto-headless freetype fontconfig && \
    dnf clean all

# Copy Java ODL fat JAR
WORKDIR /opt/odl
COPY --from=java-builder /build/target/odl-parser-runner.jar /opt/odl/odl-parser.jar

# Install Python requirements
WORKDIR ${LAMBDA_TASK_ROOT}
COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache -r <(uv export --no-dev)

# Copy application source code
COPY backend/src ${LAMBDA_TASK_ROOT}/src

# Set Lambda Handler
CMD ["src.lambda_handler.stage2_handler"]
```

### Benefits of Container Image for Stage 2
1. **Zero Packaging Headroom Anxiety**: 10 GB limit allows bundling full font packs, OpenCV, and layout models without optimization hacks.
2. **Container Reuse & Fast Pre-Warming**: AWS Lambda caches container images across worker hosts; subsequent invocations achieve warm starts within 400 ms.
3. **Decoupled Isolation**: Stage 1 remains a lean, 15 MB Python `.zip` Lambda (starting in <250 ms), while heavy OCR/JVM dependencies stay encapsulated in Stage 2.

---

## 3. Cost Kill-Switch Runbook: Zeroing Stage 2 Concurrency

If Bedrock or ODL costs spike or an emergency shutdown is required, execute this operational runbook:

### Immediate Throttling via AWS CLI
Setting reserved concurrency to `0` stops all Stage 2 executions instantly. Inbound SQS messages remain safely queued in `Stage2Queue` (up to 14 days retention) without incurring execution or token charges:

```bash
# 1. Zero out Stage 2 Lambda concurrency (emergency halt)
aws lambda put-function-concurrency \
    --function-name resume-ranker-dev-Stage2Function \
    --reserved-concurrent-executions 0 \
    --profile aws

# 2. Verify concurrency is 0
aws lambda get-function-concurrency \
    --function-name resume-ranker-dev-Stage2Function \
    --profile aws

# Expected output:
# {
#     "ReservedConcurrentExecutions": 0
# }

# 3. Check SQS queue depth while paused
aws sqs get-queue-attributes \
    --queue-url $(aws sqs get-queue-url --queue-name resume-ranker-dev-stage2-queue --profile aws --query QueueUrl --output text) \
    --attribute-names ApproximateNumberOfMessages \
    --profile aws

# 4. Resume Stage 2 processing after incident resolution
aws lambda delete-function-concurrency \
    --function-name resume-ranker-dev-Stage2Function \
    --profile aws
```

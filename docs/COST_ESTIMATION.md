# Cloud cost estimation

No AWS resources were deployed for the local demonstration. Use a selected region such as US East (N. Virginia), a dated price lookup and explicit usage assumptions when producing a monthly dollar estimate.

| Service | Estimated usage to supply |
| --- | --- |
| Glue | Runs per month × worker DPUs × actual run hours, including retries |
| Athena | Query count × measured scanned bytes, using the billing minimum and rounding |
| S3 | Average stored GB-months, retained versions, write/read requests, and data transfer |
| Lambda and SQS | Invocations, memory duration, queue requests, payload chunks and retries |
| CloudWatch | Ingested log volume, retention, metrics and alarms |
| EventBridge | Routed event and delivery counts including retries |

AWS publishes regional rates and billing units on [Glue](https://aws.amazon.com/glue/pricing/), [Athena](https://aws.amazon.com/athena/pricing/), [S3](https://aws.amazon.com/s3/pricing/) and [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/) pricing pages. This worksheet defines the model inputs. Populate it with measured cloud usage after an approved deployment.

The console illustrates monthly Glue and Athena charges in US East (N. Virginia). At 30 runs, 2 DPUs per run and 15 minutes per run, 15 DPU-hours at USD 0.44 cost USD 6.60. At 0.1 billed TB, Athena at USD 5 per TB costs USD 0.50. The USD 7.10 subtotal omits storage, networking, events, logs, taxes and retries. Rates are assumptions from an [AWS reference deployment](https://docs.aws.amazon.com/solutions/latest/guidance-for-multi-omics-and-multi-modal-data-integration-and-analysis-on-aws/cost.html), accessed November 21, 2026. This is an illustrative example.

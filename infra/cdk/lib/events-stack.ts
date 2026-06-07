import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as kinesisfirehose from 'aws-cdk-lib/aws-kinesisfirehose';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as glue from 'aws-cdk-lib/aws-glue';
import type { Construct } from 'constructs';

export class EventsStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const bucket = new s3.Bucket(this, 'EventsBucket', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    const role = new iam.Role(this, 'FirehoseRole', {
      assumedBy: new iam.ServicePrincipal('firehose.amazonaws.com'),
    });
    bucket.grantReadWrite(role);

    new kinesisfirehose.CfnDeliveryStream(this, 'EventsStream', {
      deliveryStreamName: 'pdlcflow-events',
      deliveryStreamType: 'DirectPut',
      extendedS3DestinationConfiguration: {
        bucketArn: bucket.bucketArn,
        roleArn: role.roleArn,
        prefix: 'dt=!{timestamp:yyyy-MM-dd}/',
        errorOutputPrefix: 'errors/!{firehose:error-output-type}/dt=!{timestamp:yyyy-MM-dd}/',
        bufferingHints: { sizeInMBs: 64, intervalInSeconds: 60 },
      },
    });

    new glue.CfnDatabase(this, 'GlueDb', {
      catalogId: cdk.Aws.ACCOUNT_ID,
      databaseInput: { name: 'pdlcflow_events' },
    });

    // ClickHouse Cloud peering / connection details are environment-specific
    // and live in observability-stack outputs once provisioned.
  }
}

import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as elasticache from 'aws-cdk-lib/aws-elasticache';
import * as s3 from 'aws-cdk-lib/aws-s3';
import type { Construct } from 'constructs';

interface Props extends cdk.StackProps {
  vpc: ec2.IVpc;
}

export class DataStack extends cdk.Stack {
  public readonly cluster: rds.DatabaseCluster;

  constructor(scope: Construct, id: string, props: Props) {
    super(scope, id, props);

    this.cluster = new rds.DatabaseCluster(this, 'Aurora', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_17_1,
      }),
      vpc: props.vpc,
      serverlessV2MinCapacity: 0.5,
      serverlessV2MaxCapacity: 8,
      writer: rds.ClusterInstance.serverlessV2('Writer'),
      readers: [rds.ClusterInstance.serverlessV2('Reader', { scaleWithWriter: true })],
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    new elasticache.CfnReplicationGroup(this, 'Redis', {
      replicationGroupDescription: 'pdlcflow pub/sub + rate-limit + arq',
      engine: 'redis',
      cacheNodeType: 'cache.t4g.medium',
      numCacheClusters: 2,
      automaticFailoverEnabled: true,
    });

    new s3.Bucket(this, 'Artifacts', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      versioned: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    new s3.Bucket(this, 'Events', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      lifecycleRules: [{ expiration: cdk.Duration.days(365 * 2) }],
    });
  }
}

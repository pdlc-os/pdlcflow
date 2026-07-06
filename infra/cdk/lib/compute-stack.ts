import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecs_patterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as rds from 'aws-cdk-lib/aws-rds';
import type { Construct } from 'constructs';

interface Props extends cdk.StackProps {
  vpc: ec2.IVpc;
  db: rds.IDatabaseCluster;
}

export class ComputeStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: Props) {
    super(scope, id, props);

    const cluster = new ecs.Cluster(this, 'Cluster', { vpc: props.vpc });

    // Image is overridable per deploy: `cdk deploy -c apiImage=ghcr.io/...:1.13.0`.
    // (Was a hardcoded `placeholder/pdlc-engine:phase-a` — undeployable.)
    const apiImage: string =
      this.node.tryGetContext('apiImage') ?? 'ghcr.io/pdlc-os/pdlcflow-api:latest';

    new ecs_patterns.ApplicationLoadBalancedFargateService(this, 'Api', {
      cluster,
      cpu: 512,
      memoryLimitMiB: 1024,
      desiredCount: 2,
      taskImageOptions: {
        image: ecs.ContainerImage.fromRegistry(apiImage),
        containerPort: 8000,
      },
      publicLoadBalancer: true,
    });

    // Worker — separate Fargate service running Arq, no LB needed.
    const workerTask = new ecs.FargateTaskDefinition(this, 'WorkerTask', { cpu: 512, memoryLimitMiB: 1024 });
    workerTask.addContainer('Worker', {
      image: ecs.ContainerImage.fromRegistry(apiImage),
      command: ['uv', 'run', 'arq', 'app.worker.arq_settings.WorkerSettings'],
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'worker' }),
    });
    new ecs.FargateService(this, 'WorkerService', {
      cluster,
      taskDefinition: workerTask,
      desiredCount: 2,
    });
  }
}

import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import type { Construct } from 'constructs';

export class BedrockStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Role assumed by the engine + worker tasks to invoke Bedrock in
    // shared-account mode. BYOA tenants assume their own role via STS;
    // those policies are created at tenant onboarding, not here.
    new iam.Role(this, 'EngineBedrockRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      inlinePolicies: {
        invokeBedrock: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              actions: [
                'bedrock:InvokeModel',
                'bedrock:InvokeModelWithResponseStream',
                'bedrock:Converse',
                'bedrock:ConverseStream',
              ],
              resources: ['*'],
            }),
          ],
        }),
      },
    });
  }
}

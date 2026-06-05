#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';

import { NetworkStack } from '../lib/network-stack';
import { DataStack } from '../lib/data-stack';
import { ComputeStack } from '../lib/compute-stack';
import { EdgeStack } from '../lib/edge-stack';
import { AuthStack } from '../lib/auth-stack';
import { EventsStack } from '../lib/events-stack';
import { BedrockStack } from '../lib/bedrock-stack';
import { ObservabilityStack } from '../lib/observability-stack';

const app = new cdk.App();
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
};

const network = new NetworkStack(app, 'pdlcflow-network', { env });
const data    = new DataStack(app, 'pdlcflow-data', { env, vpc: network.vpc });
new ComputeStack(app, 'pdlcflow-compute', { env, vpc: network.vpc, db: data.cluster });
new EdgeStack(app, 'pdlcflow-edge', { env });
new AuthStack(app, 'pdlcflow-auth', { env });
new EventsStack(app, 'pdlcflow-events', { env });
new BedrockStack(app, 'pdlcflow-bedrock', { env });
new ObservabilityStack(app, 'pdlcflow-observability', { env });

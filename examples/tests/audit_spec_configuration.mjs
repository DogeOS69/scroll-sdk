import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';
// Usage: node examples/tests/audit_spec_configuration.mjs /path/to/built/scroll-sdk-cli
// Diagnostic probes: false/unchanged observations are audit findings, not passing deployment checks.
if (!process.argv[2])
    throw new Error('Pass a built scroll-sdk-cli checkout as the only argument');
const cli = path.resolve(process.argv[2]);
const require = createRequire(path.join(cli, 'package.json'));
const yaml = require('js-yaml');
const toml = require('@iarna/toml');
const generator = await import(pathToFileURL(path.join(cli, 'dist/utils/deployment-spec-generator.js')));
const { generateValuesFiles } = await import(pathToFileURL(path.join(cli, 'dist/utils/values-generator.js')));
const { resolveProofIntent } = await import(pathToFileURL(path.join(cli, 'dist/utils/proof-intent.js')));
const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'spec-configuration-audit.'));
fs.chmodSync(scratch, 0o700);
try {
    // Never load an operator spec, dotenv file, key, or existing deployment.
    let fixture = fs.readFileSync(path.join(cli, 'src/config/deployment-spec.minimal.yaml'), 'utf8');
    fixture = fixture.replaceAll('$ENV:OWNER_ADDRESS', '0x0000000000000000000000000000000000000001');
    fixture = fixture.replace(/\$ENV:[A-Za-z_][A-Za-z_0-9]*/g, 'NONFUNCTIONAL_AUDIT_PLACEHOLDER');
    const spec = generator.normalizeDeploymentSpec(yaml.load(fixture));
    spec.infrastructure = { provider: 'local', sequencerCount: 1, bootnodeCount: 1 };
    spec.bridge.seedString = 'NONFUNCTIONAL_AUDIT_SEED';
    spec.frontend.baseDomain = 'audit.invalid';
    spec.dogecoin.externalRpc.url = 'https://dogecoin.audit.invalid';
    const validate = value => generator.validateDeploymentSpec(value).valid;
    assert.equal(validate(spec), true);
    const configs = value => generator.generateAllConfigs(value);
    const values = value => Object.fromEntries(Object.entries(generateValuesFiles(value)).map(([key, value]) => [key, yaml.load(value)]));
    const base = configs(spec);
    const baseValues = values(spec);
    const report = { cliRevision: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: cli, encoding: 'utf8' }).trim(), cliTree: execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { cwd: cli, encoding: 'utf8' }).trim(), cliWorkingTreeDirty: Boolean(execFileSync('git', ['status', '--porcelain'], { cwd: cli, encoding: 'utf8' }).trim()), checks: {} };
    const changed = mutation => { const copy = structuredClone(spec); mutation(copy); return copy; };
    const allOutput = value => JSON.stringify({ configs: configs(value), values: values(value) });
    const projectionOutcome = value => {
        try { return { allGeneratedOutputsUnchanged: allOutput(value) === allOutput(spec), generationRejected: false }; }
        catch { return { allGeneratedOutputsUnchanged: null, generationRejected: true }; }
    };
    const domains = changed(s => { s.frontend.hosts.rpcGateway = 'custom-rpc.audit.invalid'; });
    report.checks.domainProjection = { valid: validate(domains), configContainsHost: configs(domains)['config.toml'].includes('custom-rpc.audit.invalid'), valuesContainHost: JSON.stringify(values(domains)).includes('custom-rpc.audit.invalid') };
    const endpoint = changed(s => { s.dogecoin.kubernetes = { serviceName: 'custom-doge-audit', rpcPort: 29999 }; });
    report.checks.dogecoinDiscovery = { valid: validate(endpoint), dogeConfigHasKubernetes: Boolean(toml.parse(configs(endpoint)['doge-config.toml']).kubernetes), directValuesRpc: values(endpoint)['l1-interface-production.yaml'].configMaps.env.data.DOGEOS_L1_INTERFACE_DOGECOIN_RPC__URL };
    const da = changed(s => { Object.assign(s.ethereumDa, { confirmationDepth: 7, finalizationDepth: 99, fetchLimit: 12345, l2RpcUrl: 'http://custom-l2.audit.invalid:8545', maxFeePerGasWei: '777777', lifecycleDbPath: '/data/audit-lifecycle.sqlite' }); });
    report.checks.daOverrides = { valid: validate(da), basicConfigsUnchanged: JSON.stringify(configs(da)) === JSON.stringify(base), directValuesChanged: JSON.stringify(values(da)) !== JSON.stringify(baseValues), directFinalizationDepth: values(da)['eth-da-submitter-production.yaml'].configMaps.env.data.DOGEOS_ETH_DA_SUBMITTER_ETHEREUM__FINALIZATION_DEPTH };
    const keyset = changed(s => { s.bridge.initialAttestationKeyset = { signerIds: ['audit-a', 'audit-b', 'audit-c'], threshold: 2 }; });
    const invalidKeyset = changed(s => { s.bridge.initialAttestationKeyset = { signerIds: ['audit-a'], threshold: 99 }; });
    report.checks.initialAttestationKeyset = { valid: validate(keyset), allGeneratedOutputsUnchanged: allOutput(keyset) === allOutput(spec), impossibleThresholdAccepted: validate(invalidKeyset) };
    const tso = changed(s => { s.signing.tsoServiceUrl = 'https://custom-tso.audit.invalid'; });
    report.checks.tsoUrl = { valid: validate(tso), ...projectionOutcome(tso) };
    const unknown = changed(s => { s.ethereumDa.confirmationDepht = 7; });
    report.checks.unknownField = { valid: validate(unknown), ...projectionOutcome(unknown) };
    const buckets = changed(s => { s.ethereumDa.blobArchive = { s3: { enabled: true, bucket: 'audit-shared-placeholder', region: 'us-west-2', keyPrefix: 'blobs', publicBaseUrl: 'https://archive.audit.invalid' } }; s.proofArtifacts = { s3: { bucket: 'audit-shared-placeholder', region: 'us-west-2', keyPrefix: 'proofs' } }; });
    let sameBucketGenerationSucceeded = false;
    try { sameBucketGenerationSucceeded = Boolean(configs(buckets)); } catch { /* Rejection is a repaired-candidate observation. */ }
    report.checks.sameBucket = { valid: validate(buckets), generationSucceeded: sameBucketGenerationSucceeded };
    report.checks.defaultImageTags = Object.fromEntries(['withdrawal-processor', 'l1-interface', 'tso-service', 'cubesigner-signer', 'eth-da-submitter', 'fee-oracle', 'l2-reth-sequencer'].map(name => [name, baseValues[`${name}-production.yaml`]?.image?.tag]));
    report.checks.outputFiles = Object.keys(baseValues);
    const generatedMain = toml.parse(base['config.toml']);
    report.checks.launchDefaults = {
        rethGasLimit: baseValues['l2-reth-sequencer-production.yaml'].reth.builderGasLimit,
        rethBlockTimeMs: baseValues['l2-reth-sequencer-production.yaml'].reth.sequencer.blockTimeMs,
        rethPayloadBuildingDurationMs: baseValues['l2-reth-sequencer-production.yaml'].reth.sequencer.payloadBuildingDurationMs,
        genesisGasLimitPresent: generatedMain.genesis.GAS_LIMIT !== undefined,
        baseFeeOverheadPresent: generatedMain.contracts.L2_BASE_FEE_OVERHEAD !== undefined,
        feeOracleWriteModePresent: baseValues['fee-oracle-production.yaml'].configMaps.env.data.DOGEOS_FEE_ORACLE_ETHEREUM_DA__CONTRACT_WRITE_MODE !== undefined,
    };
    const dstack = changed(s => { s.dstackController = { enabled: true, database: { type: 'sqlite' } }; });
    report.checks.dstack = { valid: validate(dstack), dogeConfigHasController: Boolean(toml.parse(configs(dstack)['doge-config.toml']).dstackController), controllerValues: Boolean(values(dstack)['dstack-controller-production.yaml']), monitorOverlay: Boolean(values(dstack)['scroll-monitor-dstack.yaml']), baseMonitor: Boolean(values(dstack)['scroll-monitor-production.yaml']) };
    const proof = changed(s => { s.proofTopology = { mode: 'disabled', generation: 'mock', enforcement: 'observe', observeRealProofDeadlineMs: 1800000, compiler: { image: { repository: 'audit.invalid/compiler', digest: `sha256:${'a'.repeat(64)}` }, identityFilePath: '.data/audit-identity.json' }, deployment: { artifactKeyPrefix: 'audit' }, active: { profile: 'withdrawal_mock_prover', artifactStore: { kind: 'local_fs' }, workerLaunch: 'local_cpu', realScroll: {} } }; });
    assert.equal(validate(proof), true);
    const input = path.join(scratch, 'intent.yaml');
    fs.writeFileSync(input, yaml.dump(proof), { mode: 0o600 });
    const out = path.join(scratch, 'deployment');
    execFileSync(process.execPath, [path.join(cli, 'bin/run.js'), 'setup', 'generate-from-spec', '--spec', input, '--output', out, '--with-values', '--json'], { cwd: scratch, env: { PATH: process.env.PATH, OCLIF_TEST_ROOT: cli }, stdio: 'pipe' });
    const doge = toml.parse(fs.readFileSync(path.join(out, '.data/doge-config.toml'), 'utf8'));
    report.checks.proofHandoff = { actualCliSucceeded: true, specCopiedToOutput: fs.existsSync(path.join(out, 'deployment-spec.yaml')), dogeConfigHasProof: Boolean(doge.proof_topology), implicitSourceFound: Boolean(resolveProofIntent({ deploymentDir: out, dogeConfig: doge, required: false })), explicitSource: resolveProofIntent({ deploymentDir: out, dogeConfig: doge, specPath: input, required: true }).source.kind };
    fs.copyFileSync(input, path.join(out, 'deployment-spec.yaml'));
    report.checks.proofHandoff.conventionalNameSource = resolveProofIntent({ deploymentDir: out, dogeConfig: doge, required: true }).source.kind;
    report.checks.nativeServiceFiles = { wp: fs.existsSync(path.join(out, 'withdrawal-processor/WithdrawalProcessor.toml')), pc: fs.existsSync(path.join(out, 'proof-coordinator/ProofCoordinator.toml')), genesis: fs.existsSync(path.join(out, 'values/genesis.yaml')), monitor: fs.existsSync(path.join(out, 'values/scroll-monitor-production.yaml')) };
    console.log(JSON.stringify(report, null, 2));
}
finally {
    fs.rmSync(scratch, { recursive: true, force: true });
}

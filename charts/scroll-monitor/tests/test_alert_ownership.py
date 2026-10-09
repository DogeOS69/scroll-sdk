"""One rule owner per duplicate condition, with cluster coverage retained."""
import unittest
from test_monitoring_templates import render, resource

class OwnershipTests(unittest.TestCase):
    def test_retired_rules_are_not_deployed_and_diagnostics_are_enabled(self):
        docs=render('--set','grafanaAlerting.enabled=false')
        groups=[g for d in docs if d['kind']=='PrometheusRule' for g in d['spec']['groups']]
        names={r['alert'] for g in groups for r in g['rules'] if 'alert' in r}
        retired={'TargetDown','CPUThrottlingHigh','NodeCPUHighUsage','NodeMemoryHighUtilization',
                 'NodeFilesystemSpaceFillingUp','NodeFilesystemAlmostOutOfSpace','NodeFilesystemAlmostOutOfFiles',
                 'KubePersistentVolumeFillingUp','KubePersistentVolumeInodesFillingUp','KubePodCrashLooping',
                 'KubeDeploymentReplicasMismatch','KubeStatefulSetReplicasMismatch','KubeJobFailed',
                 'BusinessPodRepeatedRestarts','DstackControllerUnavailable'}
        self.assertFalse(names & retired)
        self.assertFalse(any(n.endswith('MetricsTargetDown') and n!='MetricsTargetDown' for n in names))
        self.assertFalse(any(n.endswith('PodNotReady') and n not in {'BusinessPodNotReady','KubePodNotReady'} for n in names))
        self.assertTrue({'MetricsTargetDown','KubePodNotReady','BusinessPodNotReady','PVCInodesFillingUp'} <= names)
        self.assertEqual(sum(len(g['rules']) for g in groups if g['name'].startswith('dogeos.services.')),91)

    def test_global_replacements_do_not_keep_a_business_namespace_filter(self):
        docs=render('--set','grafanaAlerting.enabled=false','--set-string','businessPodAlerts.podNameRegex=business-.*')
        groups=resource(docs,'PrometheusRule','scroll-monitor-dogeos')['spec']['groups']
        rules={r['alert']:r for g in groups for r in g['rules']}
        for name in ['BusinessPodCrashLooping','BusinessPodNotReady','BusinessDeploymentUnavailable',
                     'BusinessStatefulSetUnavailable','BusinessJobFailed','ContainerCPUThrottlingHigh','PVCUsageHigh']:
            with self.subTest(alert=name):
                self.assertNotIn('namespace="monitoring"',rules[name]['expr'])
                self.assertNotIn('business-.*',rules[name]['expr'])
        self.assertIn('phase="Running"',rules['BusinessPodNotReady']['expr'])

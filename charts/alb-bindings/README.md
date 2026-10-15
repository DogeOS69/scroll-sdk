# Existing ALB bindings

This chart connects Kubernetes Services to **existing** HTTP/IP target groups.
It renders only `elbv2.k8s.aws/v1beta1` `TargetGroupBinding` resources. ALBs,
listeners, certificates, listener rules, target groups and security groups are
provisioned and managed independently of this Helm release.

The AWS Load Balancer Controller and its CRD must already be installed. Pod IPs
must be reachable from the selected ALB. Configure ALB/backend security groups
and application NetworkPolicies separately; this chart does not modify them.

Generate values using the paired scroll-sdk-cli existing ALB support, install
the application Services, then run `make install-alb-bindings`. Its read-only
`scrollsdk setup alb --require-services` preflight checks the selected AWS
resources, route restrictions, Kubernetes context, CRD and Service ports.

Each entry in `bindings` has:

| Field | Meaning |
| --- | --- |
| `targetGroupARN` | Existing HTTP/IP target group, attached to the selected ALB |
| `targetType` | Must be `ip` |
| `serviceRef.name` | Actual Service name in the Helm release namespace |
| `serviceRef.port` | Numeric Kubernetes Service port, not a guessed Pod port |

Targets are registered dynamically by the controller. Use one target group per
binding; this chart does not support sharing target groups with other clusters,
manual targets or other bindings. The controller assumes exclusive target
membership. Keep ordinary application Ingresses disabled and use ClusterIP
Services, otherwise a separate controller reconciliation could create an ALB.

`helm uninstall alb-bindings` removes the bindings and the controller deregisters
their targets. It does **not** delete the externally managed ALB, listener,
rules or target groups. There are no deletion hooks or `keep` annotations.
Uninstalling an application stops that application's traffic; the external ALB
remains. Reinstall the application and bindings to register the new Pod targets.
Keep the controller running until binding deletion/finalizer cleanup finishes.

Application-only removal does not remove this separate binding release. Use
`make delete-alb-bindings` for the complete binding set, or update the spec and
regenerate/upgrade the release when intentionally removing one binding. Do not
reuse a retained Service name for an unrelated application while its binding
remains installed.

The chart has no AWS credentials or AWS create/delete operations. Its default
empty map renders no resources. Example identifiers in `ci/` are nonfunctional.
See [deployment configuration](../../../examples/existing-alb.md).

References:
- [AWS TargetGroupBinding patterns](https://aws.amazon.com/blogs/containers/patterns-for-targetgroupbinding-with-aws-load-balancer-controller/)
- [Controller TargetGroupBinding reference](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/targetgroupbinding/targetgroupbinding/)

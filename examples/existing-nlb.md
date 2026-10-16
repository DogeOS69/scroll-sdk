# Existing NLBs for bootnodes

Prepare one infrastructure-owned NLB per bootnode. Keep each NLB, Elastic IP,
listener, target group and frontend security group outside application Helm
releases. A bootnode reinstall then replaces only Pod registrations, not its
public endpoint. This uses the same ownership model as [existing ALBs](existing-alb.md),
but TCP P2P does not use HTTP Ingress, HTTPS certificates or ALB routing.

## Infrastructure owner

1. Choose public IPv4 subnets in the deployment's AWS account and region, and
   allocate one EIP per selected subnet. Enable the AZ containing the bootnode
   Pod and its EBS volume; cross-zone forwarding cannot enable an omitted AZ.
   With multiple enabled AZs and a single Pod, enable cross-zone forwarding so
   all advertised EIPs reach that Pod. Preserve subnet/EIP mappings in the spec.
2. Create the internet-facing NLB **with its frontend security group attached**.
   An NLB created without security groups cannot have them attached later.
   Permit only TCP 30303 from the approved partner IPv4 CIDRs. Review all attached
   security groups together; do not add an alternate open IPv4/IPv6, prefix-list,
   or security-group source that bypasses that allowlist. Partner CIDRs describe
   their P2P nodes' public egress, not necessarily their attestation signers.
3. Create a dedicated TCP, port 30303, IP target group in the cluster VPC, with TCP
   health checks on `traffic-port`. Disable Proxy Protocol v2: RLPx is not a Proxy
   Protocol or TLS listener. Configure TCP 30303 to forward to this target group.
   Do not share a target group between bindings, nodes, clusters or manual targets.
4. Install AWS Load Balancer Controller with TargetGroupBinding support and the
   permissions needed to register targets and reconcile backend security groups.
   Permit frontend SG egress and backend/pod network paths for traffic and health
   checks. The binding supplies NLB SG sources on TCP 30303 for backend ingress;
   frontend allowlist rules remain infrastructure-owned.
5. Persist each bootnode's original node key in an external Secret. Retaining an
   EIP without its node key does not retain the enode identity. If using
   `pvcAutoGenerate`, deleting its data PVC loses that key; use `nodeKey.mode: secret`
   for reinstalls that discard node data.

No Cloudflare operation is necessary when partners use an EIP-based enode.
Optional DNS records must be DNS only; ordinary Cloudflare HTTP proxying does not
carry TCP 30303. Partners need the node's public key, EIP and port, not AWS access.

## Application configuration

The CLI's `bootnodePublicP2p` entry uses `mode: existing` and `existingNlb` fields
`loadBalancerArn`, `listenerArn`, `targetGroupArn`, and `securityGroupIds`.
Generated Helm values use the uppercase `ARN` field names shown here. Populate
real infrastructure identifiers; the chart CI fixture uses synthetic values.

```yaml
role: bootnode
reth:
  nodeKey:
    mode: secret
  p2pExternal:
    enabled: true
    mode: existing
    ordinal: 0
    sourceRanges: [203.0.113.10/32] # Replace with the approved partner egress CIDR.
    allowOpenPeering: false
    subnets: [REPLACE_WITH_PUBLIC_SUBNET_ID]
    eipAllocations: [REPLACE_WITH_EIP_ALLOCATION_ID]
    annotations: {}
    existingNlb:
      loadBalancerARN: REPLACE_WITH_NLB_ARN
      listenerARN: REPLACE_WITH_TCP_30303_LISTENER_ARN
      targetGroupARN: REPLACE_WITH_TCP_IP_TARGET_GROUP_ARN
      securityGroupIds: [REPLACE_WITH_NLB_SECURITY_GROUP_ID]
```

Install the generated bootnode values with its normal Makefile target. The chart
creates `<fullname>-p2p`, a ClusterIP Service with only TCP 30303 and one Pod's
selector, plus a TargetGroupBinding in the same release. RPC, WS and metrics
remain internal. `sourceRanges` is checked intent, not a Service firewall in this
mode; validate the external frontend SG before installing.

## Migration and lifecycle acceptance

Do not simply change an existing LoadBalancer Service to ClusterIP expecting its
old NLB to remain: the Controller owns that old NLB and may delete it. Schedule a
migration, preserve the node key, and prepare the new independently owned NLB and
its references first. Reusing the old EIP requires waiting for its old NLB to be
deleted and the EIP disassociated; otherwise allocate a new EIP and coordinate a
partner enode update. Do not remove finalizers to skip cleanup.

For each bootnode, verify on a disposable or explicitly authorized deployment:

1. Installation registers exactly the intended Pod in its target group; both TCP
   health and a real RLPx peer handshake work from an allowed partner source.
2. A denied source cannot reach P2P. Public RPC, WS and metrics remain unreachable.
3. Uninstall removes the binding and Service and deregisters its Pod. Keep the
   Controller running until binding finalizers finish. Confirm NLB, listener,
   target group, EIPs and frontend SG rules remain; the other bootnode still works.
4. Reinstall with the same external key and infrastructure references. The new Pod
   registers, becomes healthy, and peers reconnect to the original enode.

Offline Helm tests verify resource ownership, selectors, binding ports and
validation errors. They do not establish AWS connectivity, frontend filtering,
controller permissions or successful uninstall/reinstall; record those separately.

# Independent bootnode NLB: from an EKS cluster to partner access

This reference deployment uses one infrastructure-owned NLB per externally
reachable, non-sequencer Reth bootnode. Each endpoint selects one Pod and one
persistent node identity. This
runbook starts with an existing EKS cluster and creates the missing networking
resources; it does not assume an NLB already exists.

**Partner allowlists belong only to AWS infrastructure.** Neither deployment
spec nor production YAML contains partner CIDRs in `mode: existing`. Adding or
removing a partner changes the NLB frontend security group, without regenerating
values, upgrading Helm or restarting Reth. If Terraform/CloudFormation owns these
resources, make the equivalent change there; do not create a second configuration
owner with ad-hoc CLI edits.

No Cloudflare, DNS record, ACM certificate, ALB or Ingress is required. Give partners
`enode://<node-public-key>@<EIP>:30303`. This is TCP RLPx, not HTTPS. Ordinary
Cloudflare HTTP proxying cannot carry it. Optional custom DNS is DNS-only and
requires client support; it is outside this EIP-based procedure.

## Ownership and scope

| Owner | Responsibility |
| --- | --- |
| AWS infrastructure | Public subnet/routes, EIP, NLB, listener, target group, frontend SG and partner approval/change history; Controller IAM and installation |
| Application deployment | Persistent node key, Pod/EBS placement, dedicated ClusterIP Service and TargetGroupBinding referencing AWS resources |
| AWS Load Balancer Controller | Register/deregister the selected Pod IP and reconcile backend ingress from the referenced NLB SG |
| Partner | Supply actual public egress CIDRs (including NAT), configure the provided bootnode enodes as static/trusted peers, verify block synchronization |

The NLB publishes only TCP 30303. RPC, WS and metrics remain internal. Do not put
multiple node identities behind one endpoint or manually register target IPs.
AWS resources survive application Helm uninstall; the Controller must remain
running until binding finalizers finish deregistering the Pod.

Use l2-reth **0.1.11 or later with this interface**, plus the paired CLI changes.
Older releases require duplicated `sourceRanges` and cannot use this contract.
Remove old nonempty lists from existing-mode spec/values once when adopting this
interface; subsequent partner changes are AWS-only. Service-owned NLBs retain
configuration-owned allowlists; see [mode selection](bootnode-public-p2p.md).

## 1. Establish the cluster, account and workspace

Run these Bash examples from a private operator directory outside the SDK
checkout. Install AWS CLI v2, kubectl, Helm, eksctl, curl and jq. Replace all
`REPLACE_*` values. These are provisioning commands, not a dry run; record each
returned ID and resume from the last completed step rather than allocating again.
No credentials or node private keys belong in this repository.

```bash
set -euo pipefail
umask 077
P2P_PROFILE='REPLACE_AWS_PROFILE'
P2P_REGION='REPLACE_AWS_REGION'
P2P_CLUSTER='REPLACE_EKS_CLUSTER'
P2P_CONTEXT="${P2P_CLUSTER}-p2p-operator"
P2P_WORK_DIR='REPLACE_ABSOLUTE_PRIVATE_OPERATOR_DIRECTORY'
mkdir -p "$P2P_WORK_DIR"
P2P_AWS=(aws --profile "$P2P_PROFILE" --region "$P2P_REGION" --no-cli-pager)
P2P_KUBECONFIG="$P2P_WORK_DIR/kubeconfig"
P2P_KUBE=(kubectl --kubeconfig "$P2P_KUBECONFIG" --context "$P2P_CONTEXT")

"${P2P_AWS[@]}" sts get-caller-identity
"${P2P_AWS[@]}" eks describe-cluster --name "$P2P_CLUSTER" \
  --query 'cluster.{Status:status,Version:version,VPC:resourcesVpcConfig.vpcId,Subnets:resourcesVpcConfig.subnetIds}'
P2P_VPC_ID=$("${P2P_AWS[@]}" eks describe-cluster --name "$P2P_CLUSTER" \
  --query 'cluster.resourcesVpcConfig.vpcId' --output text)
"${P2P_AWS[@]}" eks update-kubeconfig --name "$P2P_CLUSTER" \
  --alias "$P2P_CONTEXT" --kubeconfig "$P2P_KUBECONFIG"
"${P2P_KUBE[@]}" get nodes -L topology.kubernetes.io/zone
"${P2P_KUBE[@]}" -n kube-system get deployment aws-load-balancer-controller --ignore-not-found
```

Confirm the account/region before creation. The cluster needs schedulable compute,
working VPC CNI/networking and, for Reth EBS volumes, the EBS CSI driver and a suitable
StorageClass. A control-plane-only cluster cannot run the Controller or Reth yet.
The operator needs EC2/ELB provisioning permissions, IAM/CloudFormation permissions
for the Controller setup, and Kubernetes administrative access. The runtime
Controller uses its own IAM role, not the operator's credentials.

## 2. Select or create a public subnet

For each node choose a public subnet in the cluster VPC and in its planned Pod/EBS
AZ. Existing private Pod subnets can stay private. Review subnet CIDRs, route-table
associations (including the VPC main table), Internet Gateway and NACLs:

```bash
"${P2P_AWS[@]}" ec2 describe-subnets --filters "Name=vpc-id,Values=$P2P_VPC_ID" \
  --query 'Subnets[].{Id:SubnetId,AZ:AvailabilityZone,CIDR:CidrBlock,FreeIPs:AvailableIpAddressCount}'
"${P2P_AWS[@]}" ec2 describe-route-tables --filters "Name=vpc-id,Values=$P2P_VPC_ID"
"${P2P_AWS[@]}" ec2 describe-internet-gateways \
  --filters "Name=attachment.vpc-id,Values=$P2P_VPC_ID"
```

A subnet is public when its effective route table has an active `0.0.0.0/0` route
to the VPC Internet Gateway; a NAT gateway or a public-sounding name is not enough.
Reserve sufficient free addresses (AWS requires at least eight for an internet-facing
NLB subnet). NACLs must permit the listener, backend and return traffic.

If a suitable subnet exists, set `P2P_SUBNET_ID` to its ID and skip creation below.
Otherwise choose an **unused CIDR inside the VPC CIDR** with the network owner:

```bash
P2P_AZ='REPLACE_BOOTNODE_AZ'
P2P_PUBLIC_CIDR='REPLACE_UNUSED_VPC_SUBNET_CIDR'
P2P_IGW_ID='REPLACE_EXISTING_ATTACHED_IGW_ID'

# Only if the VPC has no Internet Gateway, create and attach one instead:
# P2P_IGW_ID=$("${P2P_AWS[@]}" ec2 create-internet-gateway \
#   --query 'InternetGateway.InternetGatewayId' --output text)
# "${P2P_AWS[@]}" ec2 attach-internet-gateway \
#   --internet-gateway-id "$P2P_IGW_ID" --vpc-id "$P2P_VPC_ID"

P2P_SUBNET_ID=$("${P2P_AWS[@]}" ec2 create-subnet --vpc-id "$P2P_VPC_ID" \
  --availability-zone "$P2P_AZ" --cidr-block "$P2P_PUBLIC_CIDR" \
  --query 'Subnet.SubnetId' --output text)
P2P_ROUTE_TABLE_ID=$("${P2P_AWS[@]}" ec2 create-route-table --vpc-id "$P2P_VPC_ID" \
  --query 'RouteTable.RouteTableId' --output text)
"${P2P_AWS[@]}" ec2 create-route --route-table-id "$P2P_ROUTE_TABLE_ID" \
  --destination-cidr-block 0.0.0.0/0 --gateway-id "$P2P_IGW_ID"
"${P2P_AWS[@]}" ec2 associate-route-table --subnet-id "$P2P_SUBNET_ID" \
  --route-table-id "$P2P_ROUTE_TABLE_ID"
```

This associates only the new subnet; do not replace existing application routes.
Explicit subnet selection below does not rely on Controller subnet discovery tags.

## 3. Install the Controller once per cluster, if absent

Reuse an existing supported Controller and its identity. Do not install a second
Controller or overwrite an existing service account. For a new installation,
select a reviewed chart version compatible with the cluster, inspect its
`appVersion`, and use that exact release's IAM policy. EKS Auto Mode requires its
own ownership/CRD review; this procedure uses the standard AWS Load Balancer
Controller and `elbv2.k8s.aws/v1beta1` TargetGroupBindings.

```bash
P2P_LBC_CHART_VERSION='REPLACE_REVIEWED_CHART_VERSION'
P2P_LBC_VERSION='REPLACE_MATCHING_APP_VERSION_WITH_V_PREFIX'
P2P_POLICY_NAME='REPLACE_UNIQUE_CONTROLLER_POLICY_NAME'
helm repo add eks https://aws.github.io/eks-charts
helm repo update eks
helm show chart eks/aws-load-balancer-controller --version "$P2P_LBC_CHART_VERSION"

# Inspect the chosen release's prerequisites, including any Gateway API CRDs.
# Complete those prerequisites before the Helm install below.
curl --fail --location \
  "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/${P2P_LBC_VERSION}/docs/install/iam_policy.json" \
  --output "$P2P_WORK_DIR/lbc-iam-policy.json"
# Review this policy before creating it. Reuse its ARN if already provisioned.
P2P_POLICY_ARN=$("${P2P_AWS[@]}" iam create-policy --policy-name "$P2P_POLICY_NAME" \
  --policy-document "file://$P2P_WORK_DIR/lbc-iam-policy.json" \
  --query 'Policy.Arn' --output text)
eksctl utils associate-iam-oidc-provider --profile "$P2P_PROFILE" \
  --region "$P2P_REGION" --cluster "$P2P_CLUSTER" --approve
eksctl create iamserviceaccount --profile "$P2P_PROFILE" \
  --region "$P2P_REGION" --cluster "$P2P_CLUSTER" \
  --namespace kube-system --name aws-load-balancer-controller \
  --attach-policy-arn "$P2P_POLICY_ARN" --approve
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  --kubeconfig "$P2P_KUBECONFIG" --kube-context "$P2P_CONTEXT" \
  --namespace kube-system --version "$P2P_LBC_CHART_VERSION" \
  --set clusterName="$P2P_CLUSTER" --set region="$P2P_REGION" --set vpcId="$P2P_VPC_ID" \
  --set serviceAccount.create=false --set serviceAccount.name=aws-load-balancer-controller \
  --wait --timeout 5m
"${P2P_KUBE[@]}" get crd targetgroupbindings.elbv2.k8s.aws
"${P2P_KUBE[@]}" -n kube-system rollout status deployment/aws-load-balancer-controller
```

See the [AWS installation guide](https://docs.aws.amazon.com/eks/latest/userguide/lbc-helm.html)
and [IRSA prerequisites](https://docs.aws.amazon.com/eks/latest/userguide/enable-iam-roles-for-service-accounts.html).
A Helm install supplies the Controller CRDs; upgrades require following the selected
release's CRD upgrade instructions. Allow the EKS control plane to reach the
Controller webhook (normally TCP 9443), and the Controller to reach AWS APIs.
Backend SG reconciliation must be authorized. The binding permits TCP 30303 from
the NLB SG; it does not override restrictive NACLs or Kubernetes NetworkPolicies.

## 4. Create one independent NLB per bootnode

Repeat this section for every public bootnode, using a unique short name (NLB and
TG names have a 32-character limit), dedicated EIP, NLB, TG and frontend SG. Reuse
a public subnet if appropriate. This example enables one AZ containing the node's
Pod and EBS; a second bootnode in another AZ provides a separate failure domain.

```bash
P2P_NAME='REPLACE_BOOTNODE_RESOURCE_NAME'
P2P_SUBNET_ID='REPLACE_PUBLIC_SUBNET_ID'
P2P_EIP_ALLOC_ID=$("${P2P_AWS[@]}" ec2 allocate-address --domain vpc \
  --query AllocationId --output text)
P2P_SG_ID=$("${P2P_AWS[@]}" ec2 create-security-group --vpc-id "$P2P_VPC_ID" \
  --group-name "${P2P_NAME}-nlb" --description "P2P TCP30303 for ${P2P_NAME}" \
  --query GroupId --output text)
# The new SG has NO ingress: the endpoint stays closed until section 6.
# Retain default outbound access, or explicitly allow backend/health-check traffic.
P2P_NLB_ARN=$("${P2P_AWS[@]}" elbv2 create-load-balancer --name "$P2P_NAME" \
  --type network --scheme internet-facing --ip-address-type ipv4 \
  --security-groups "$P2P_SG_ID" \
  --subnet-mappings "SubnetId=${P2P_SUBNET_ID},AllocationId=${P2P_EIP_ALLOC_ID}" \
  --tags Key=ManagedBy,Value=infrastructure \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)
"${P2P_AWS[@]}" elbv2 wait load-balancer-available --load-balancer-arns "$P2P_NLB_ARN"
P2P_TG_ARN=$("${P2P_AWS[@]}" elbv2 create-target-group --name "${P2P_NAME}-p2p" \
  --protocol TCP --port 30303 --target-type ip --ip-address-type ipv4 \
  --vpc-id "$P2P_VPC_ID" --health-check-protocol TCP --health-check-port traffic-port \
  --tags Key=ManagedBy,Value=infrastructure \
  --query 'TargetGroups[0].TargetGroupArn' --output text)
"${P2P_AWS[@]}" elbv2 modify-target-group-attributes --target-group-arn "$P2P_TG_ARN" \
  --attributes Key=proxy_protocol_v2.enabled,Value=false
P2P_LISTENER_ARN=$("${P2P_AWS[@]}" elbv2 create-listener --load-balancer-arn "$P2P_NLB_ARN" \
  --protocol TCP --port 30303 \
  --default-actions "Type=forward,TargetGroupArn=${P2P_TG_ARN}" \
  --query 'Listeners[0].ListenerArn' --output text)
P2P_PUBLIC_IP=$("${P2P_AWS[@]}" ec2 describe-addresses --allocation-ids "$P2P_EIP_ALLOC_ID" \
  --query 'Addresses[0].PublicIp' --output text)
jq -n --arg name "$P2P_NAME" --arg subnet "$P2P_SUBNET_ID" \
  --arg allocation "$P2P_EIP_ALLOC_ID" --arg ip "$P2P_PUBLIC_IP" \
  --arg sg "$P2P_SG_ID" --arg nlb "$P2P_NLB_ARN" \
  --arg listener "$P2P_LISTENER_ARN" --arg tg "$P2P_TG_ARN" \
  '{name:$name,subnet:$subnet,eipAllocation:$allocation,publicIp:$ip,securityGroup:$sg,nlb:$nlb,listener:$listener,targetGroup:$tg}' \
  > "$P2P_WORK_DIR/${P2P_NAME}-resources.json"
```

Create the NLB with its SG attached; an NLB created without SGs cannot acquire
one later. Do not add Kubernetes Controller ownership tags to these independent
resources. The TG stays empty until Reth is installed. No `register-targets` call
is needed. NLB TLS termination and Proxy Protocol are incompatible with this RLPx
listener. See [NLB creation](https://docs.aws.amazon.com/cli/latest/reference/elbv2/create-load-balancer.html),
[target group creation](https://docs.aws.amazon.com/cli/latest/reference/elbv2/create-target-group.html)
and [SG behavior](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/load-balancer-security-groups.html).

For a multi-AZ NLB, allocate one EIP per subnet, pass all subnet/EIP mappings at
creation, and enable cross-zone forwarding:

```bash
"${P2P_AWS[@]}" elbv2 modify-load-balancer-attributes --load-balancer-arn "$P2P_NLB_ARN" \
  --attributes Key=load_balancing.cross_zone.enabled,Value=true
```

The TG must inherit that setting or also enable cross-zone. The Pod's AZ must be
explicitly enabled on the NLB; cross-zone cannot enable an omitted AZ. Multiple
AZs on the NLB do not make its single target Pod highly available.

## 5. Hand off AWS references and install Reth

| Infrastructure output | Production YAML under `reth.p2pExternal` |
| --- | --- |
| NLB ARN | Infrastructure receipt; CLI discovers it from TG |
| TCP 30303 listener ARN | Infrastructure receipt; CLI discovers it from NLB |
| Dedicated TCP/IP TG ARN | `existingNlb.targetGroupARN` |
| All attached frontend SG IDs | `existingNlb.securityGroupIds` |
| Public subnet IDs | Discovered from NLB; no required YAML input |
| EIP allocation IDs | Infrastructure receipt; discovered from NLB |
| Public EIP address | Partner enode handoff; not an allocation ID |
| AZ | Pod/EBS placement verification |
| Partner CIDRs | AWS infrastructure only; no spec/values field |

Merge the following into each node's full production values. Replace placeholders;
retain the existing image, genesis, storage, internal peers and other Reth settings.
`ordinal: 0` selects the first Pod of that release, not the bootnode's spec index.

```yaml
role: bootnode
reth:
  nodeKey:
    mode: secret
    secretName: REPLACE_WITH_EXISTING_NODE_KEY_SECRET
    secretKey: RETH_NODEKEY
  p2pExternal:
    enabled: true
    mode: existing
    ordinal: 0
    existingNlb:
      targetGroupARN: REPLACE_WITH_TCP_IP_TARGET_GROUP_ARN
      securityGroupIds: [REPLACE_WITH_NLB_FRONTEND_SG_ID]
```

For CLI-generated deployments put these references in `bootnodePublicP2p` with
`existingNlb.targetGroupArn` (lowercase `Arn`) and `existingNlb.securityGroupIds`.
The CLI infers existing mode from this block and discovers the other AWS details. See [spec configuration](bootnode-public-p2p.md). There is no
`sourceRanges` list in either input. Nonempty legacy lists fail with an instruction
to remove them; they never configure the external SG.

Persist the original node key in an externally managed Secret before installing.
Do not generate a new identity on reinstall or rely on a deleted data PVC. Keep
one live Pod per identity, select its AZ consistently with the NLB and EBS, and
configure its internal peers so it receives chain data. The chart disables UDP
discovery; partners connect using static/trusted peers over TCP 30303.

For a generated deployment, from its deployment directory:

```bash
scrollsdk setup bootnode-public-p2p --spec ../deployment-spec.yaml --aws-profile "$P2P_PROFILE" --dry-run
scrollsdk setup bootnode-public-p2p --spec ../deployment-spec.yaml --aws-profile "$P2P_PROFILE"
scrollsdk setup nlb --spec ../deployment-spec.yaml --aws-profile "$P2P_PROFILE"
make install-l2-reth-bootnode
scrollsdk setup nlb --spec ../deployment-spec.yaml --aws-profile "$P2P_PROFILE" --require-targets
```

The focused command requires existing indexed values and saved public identities,
updates only the listed bootnodes, and prints public enodes. It performs AWS reads
only. Any validation failure leaves original values unchanged. Unrelated values
are preserved; YAML comments/formatting may be normalized.

Review the generated Makefile's context, namespace, chart version and release list
before installation. `setup nlb` requires the deployment spec/saved intent and
matching generated values; it is not a standalone checker for arbitrary manual
values. Supply `--dir`, `--spec`, `--values-dir` if needed. It is read-only: it
checks resource references and network boundaries, not whether a company is
approved. Empty SG ingress is valid and means no external peers are admitted.
`--require-targets` additionally checks the actual binding, ready Pod/AZ and exact
healthy registered target. It does not prove RLPx or block synchronization.

For manual Helm deployments install with the deployment's normal release command
and inspect the binding and target health directly:

```bash
P2P_NAMESPACE='REPLACE_APPLICATION_NAMESPACE'
"${P2P_KUBE[@]}" -n "$P2P_NAMESPACE" get targetgroupbindings.elbv2.k8s.aws
"${P2P_AWS[@]}" elbv2 describe-target-health --target-group-arn "$P2P_TG_ARN"
```

## 6. Add or remove partners repeatedly: AWS only

Collect each partner's actual L2-node public egress IPv4 CIDRs, including NAT,
and record approval in the infrastructure change record. Signer addresses are not
necessarily their P2P-node addresses. Select the NLBs the partner may access; each
has its own SG. Keep the other partners' rules intact. A new partner does not need
a new NLB. Use the infrastructure IaC workflow if those SGs are managed by IaC.

For CLI-managed infrastructure, set the AWS variables from section 1 and append:

```bash
P2P_PARTNER_NAME='REPLACE_PARTNER_LABEL'
P2P_PARTNER_CIDR='REPLACE_APPROVED_PUBLIC_EGRESS_CIDR'
P2P_ALLOWED_SGS=('REPLACE_BOOTNODE_0_NLB_SG' 'REPLACE_BOOTNODE_1_NLB_SG')
P2P_PERMISSION=$(jq -cn --arg cidr "$P2P_PARTNER_CIDR" --arg description "$P2P_PARTNER_NAME" \
  '[{IpProtocol:"tcp",FromPort:30303,ToPort:30303,IpRanges:[{CidrIp:$cidr,Description:$description}]}]')
for P2P_ALLOWED_SG in "${P2P_ALLOWED_SGS[@]}"; do
  "${P2P_AWS[@]}" ec2 authorize-security-group-ingress \
    --group-id "$P2P_ALLOWED_SG" --ip-permissions "$P2P_PERMISSION"
done
"${P2P_AWS[@]}" ec2 describe-security-groups --group-ids "${P2P_ALLOWED_SGS[@]}" \
  --query 'SecurityGroups[].{Id:GroupId,Ingress:IpPermissions}'
```

Repeat per distinct CIDR. Duplicate rules return an error; inspect what already
exists before resuming. Review the union of rules on **all** attached SGs. Allow
only explicit IPv4 ranges on TCP 30303, never `/0`, IPv6, other ports, SG-reference
or prefix-list bypasses. Several ranges covering all IPv4 are also rejected by
CLI preflight. Broad ranges still need human approval; preflight cannot identify
the business owner of an IP. Track SG rule quotas as the partner list grows.

Revoke a previously approved CIDR on each affected SG:

```bash
for P2P_ALLOWED_SG in "${P2P_ALLOWED_SGS[@]}"; do
  "${P2P_AWS[@]}" ec2 revoke-security-group-ingress \
    --group-id "$P2P_ALLOWED_SG" --protocol tcp --port 30303 --cidr "$P2P_PARTNER_CIDR"
done
```

Check whether another rule or partner shares/contains that CIDR before revocation.
SG changes affect new connections; tracked established connections may persist.
An AWS API success response does not prove the change has propagated to the data
plane. Retest fresh connections from the removed source until they are denied,
while confirming the target remains healthy; record that result before declaring
revocation complete.
If immediate offboarding of a live peer is required, include explicit peer
disconnection and a denied-reconnection test in that operation.
See [adding rules](https://docs.aws.amazon.com/cli/latest/reference/ec2/authorize-security-group-ingress.html)
and [connection tracking](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-connection-tracking.html).

No spec edit, production YAML edit, Helm upgrade, Reth restart or Cloudflare change
is needed for an ordinary allowlist update. Rerun `scrollsdk setup nlb
--require-targets` where the CLI deployment workflow is used; it must accept new
restricted AWS CIDRs without a matching list in application configuration.
Then test a real new connection from the partner's approved egress and from a denied
source. Send the public enode and chain/genesis/client requirements to the partner.

## 7. Record acceptance separately from provisioning

For each bootnode record the AWS resource receipt, release/chart versions, public
enode, approved/denied test origins, results and timestamps in the private operator
workspace. Keep private keys and credentials out of reports.

1. The target group contains exactly the selected Pod IP/30303 and is healthy.
2. An approved partner completes an RLPx handshake with the expected identity and
   imports new blocks. A TCP probe alone is insufficient.
3. A denied source cannot establish TCP 30303. RPC/WS/metrics and UDP discovery are
   not exposed by the NLB, including to approved sources.
4. On an authorized test deployment, recreate the Pod and verify the same key/EIP
   and automatic peer reconnection. Test a second bootnode when the first is down.
5. On an authorized disposable deployment, uninstall/reinstall the application:
   only Pod registration changes; NLB, listener, TG, EIP and frontend SG persist.
   Keep the Controller alive through finalizer cleanup and reuse the external key.

Local renders and CLI preflight do not establish partner connectivity. Monitor TG
health, peer connectivity and block lag after acceptance. NLB health checks are
routing signals, not a firewall; closed/restricted SG ingress is the access boundary.

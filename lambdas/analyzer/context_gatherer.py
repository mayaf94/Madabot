"""
Infrastructure Context Gatherer
Collects AWS infrastructure context to enrich AI analysis with relevant system state.
"""

import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import boto3
from botocore.exceptions import ClientError


class ContextGatherer:
    """Gathers infrastructure context from various AWS services"""

    def __init__(self):
        self.ec2 = boto3.client('ec2')
        self.ecs = boto3.client('ecs')
        self.elbv2 = boto3.client('elbv2')
        self.cloudformation = boto3.client('cloudformation')
        self.cloudwatch = boto3.client('cloudwatch')
        self.logs = boto3.client('logs')

    def gather_all_context(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gather all relevant infrastructure context for an alert.

        Args:
            alert: Alert object containing log_group, log_stream, message, etc.

        Returns:
            Dictionary containing all gathered context
        """
        context = {
            'log_context': {},
            'compute': {},
            'load_balancers': {},
            'recent_changes': {},
            'metrics': {},
            'resource_tags': {}
        }

        # Extract log context (Pod/Node names, container IDs, etc.)
        if 'log_group' in alert and 'log_stream' in alert:
            context['log_context'] = self.extract_log_context(
                alert['log_group'],
                alert['log_stream'],
                alert.get('message', '')
            )

        # Get recent logs for context
        if 'log_group' in alert and 'log_stream' in alert:
            context['recent_logs'] = self.get_recent_logs(
                alert['log_group'],
                alert['log_stream'],
                lookback_minutes=10
            )

        # Gather compute resource status based on detected infrastructure
        infra_type = context['log_context'].get('infrastructure_type')
        resource_id = context['log_context'].get('resource_id')

        if infra_type == 'ecs' and resource_id:
            context['compute']['ecs'] = self.get_ecs_task_health(resource_id)
        elif infra_type == 'ec2' and resource_id:
            context['compute']['ec2'] = self.get_ec2_instance_status(resource_id)

        # Get load balancer health if detected
        if context['log_context'].get('load_balancer_name'):
            context['load_balancers'] = self.get_alb_target_health(
                context['log_context']['load_balancer_name']
            )

        # Get recent CloudFormation changes
        context['recent_changes'] = self.get_recent_cloudformation_changes(
            lookback_hours=24
        )

        # Get CloudWatch metrics for the service
        if 'log_group' in alert:
            context['metrics'] = self.get_cloudwatch_metrics(
                alert['log_group'],
                lookback_minutes=30
            )

        # Get resource tags for context
        if resource_id:
            context['resource_tags'] = self.get_resource_tags(resource_id, infra_type)

        return context

    def extract_log_context(
        self,
        log_group: str,
        log_stream: str,
        message: str
    ) -> Dict[str, Any]:
        """
        Extract infrastructure context from log group, stream names, and message.
        Identifies Pod names, Node names, container IDs, etc.

        Examples:
        - ECS: /aws/ecs/my-cluster/task-id
        - K8s: pod-name-abc123, node: ip-10-0-1-50
        - Lambda: /aws/lambda/function-name
        """
        context = {
            'log_group': log_group,
            'log_stream': log_stream,
            'infrastructure_type': 'unknown',
            'resource_id': None,
            'pod_name': None,
            'node_name': None,
            'container_id': None,
            'cluster_name': None,
            'task_id': None
        }

        # Detect ECS
        if '/ecs/' in log_group or '/ecs/' in log_stream:
            context['infrastructure_type'] = 'ecs'

            # Extract cluster name: /ecs/cluster-name/...
            cluster_match = re.search(r'/ecs/([^/]+)', log_group)
            if cluster_match:
                context['cluster_name'] = cluster_match.group(1)

            # Extract task ID from log stream
            task_match = re.search(r'([a-f0-9]{32})', log_stream)
            if task_match:
                context['task_id'] = task_match.group(1)
                context['resource_id'] = task_match.group(1)

        # Detect Lambda
        elif '/lambda/' in log_group:
            context['infrastructure_type'] = 'lambda'
            func_match = re.search(r'/aws/lambda/([^/]+)', log_group)
            if func_match:
                context['resource_id'] = func_match.group(1)

        # Detect EC2 (often custom log groups)
        elif 'ec2' in log_group.lower():
            context['infrastructure_type'] = 'ec2'
            # Try to extract instance ID from log stream
            instance_match = re.search(r'(i-[a-f0-9]{8,17})', log_stream)
            if instance_match:
                context['resource_id'] = instance_match.group(1)

        # Detect Kubernetes (if using FluentBit/Fluent to CloudWatch)
        # Log format: kubernetes.pod_name, kubernetes.namespace_name, kubernetes.host
        if 'kubernetes' in message.lower() or 'pod' in log_stream.lower():
            context['infrastructure_type'] = 'kubernetes'

            # Extract pod name
            pod_match = re.search(r'pod[_-]?name[:\s]+([a-z0-9-]+)', message, re.IGNORECASE)
            if pod_match:
                context['pod_name'] = pod_match.group(1)

            # Extract node name
            node_match = re.search(r'node[_-]?name[:\s]+([a-z0-9.-]+)', message, re.IGNORECASE)
            if node_match:
                context['node_name'] = node_match.group(1)

            # Extract namespace
            ns_match = re.search(r'namespace[:\s]+([a-z0-9-]+)', message, re.IGNORECASE)
            if ns_match:
                context['namespace'] = ns_match.group(1)

        # Extract container ID if present
        container_match = re.search(r'container[_-]?id[:\s]+([a-f0-9]{12,64})', message, re.IGNORECASE)
        if container_match:
            context['container_id'] = container_match.group(1)

        # Try to detect load balancer from message
        alb_match = re.search(r'(app/[a-zA-Z0-9-]+/[a-f0-9]{16})', message)
        if alb_match:
            context['load_balancer_name'] = alb_match.group(1)

        return context

    def get_recent_logs(
        self,
        log_group: str,
        log_stream: str,
        lookback_minutes: int = 10
    ) -> List[Dict[str, Any]]:
        """Fetch recent logs from the same log stream for context"""
        try:
            start_time = int((datetime.utcnow() - timedelta(minutes=lookback_minutes)).timestamp() * 1000)

            response = self.logs.get_log_events(
                logGroupName=log_group,
                logStreamName=log_stream,
                startTime=start_time,
                limit=50,  # Last 50 log entries
                startFromHead=False  # Get most recent first
            )

            return [
                {
                    'timestamp': event['timestamp'],
                    'message': event['message'][:500]  # Truncate long messages
                }
                for event in response.get('events', [])
            ]

        except ClientError as e:
            print(f"Error fetching recent logs: {e}")
            return []

    def get_ec2_instance_status(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get EC2 instance status and health checks"""
        try:
            response = self.ec2.describe_instance_status(
                InstanceIds=[instance_id],
                IncludeAllInstances=True
            )

            if not response['InstanceStatuses']:
                return None

            status = response['InstanceStatuses'][0]

            return {
                'instance_id': instance_id,
                'instance_state': status['InstanceState']['Name'],
                'system_status': status.get('SystemStatus', {}).get('Status', 'unknown'),
                'instance_status': status.get('InstanceStatus', {}).get('Status', 'unknown'),
                'events': [
                    {
                        'code': event['Code'],
                        'description': event['Description'],
                        'not_before': str(event.get('NotBefore', ''))
                    }
                    for event in status.get('Events', [])
                ]
            }

        except ClientError as e:
            print(f"Error fetching EC2 status for {instance_id}: {e}")
            return None

    def get_ecs_task_health(self, task_id: str, cluster_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get ECS task health and status"""
        try:
            # If cluster name not provided, try to find the task
            clusters_to_check = []

            if cluster_name:
                clusters_to_check = [cluster_name]
            else:
                # List all clusters
                response = self.ecs.list_clusters()
                clusters_to_check = response.get('clusterArns', [])

            for cluster in clusters_to_check:
                try:
                    response = self.ecs.describe_tasks(
                        cluster=cluster,
                        tasks=[task_id]
                    )

                    if response['tasks']:
                        task = response['tasks'][0]

                        return {
                            'task_id': task_id,
                            'cluster': cluster,
                            'task_arn': task['taskArn'],
                            'last_status': task.get('lastStatus'),
                            'desired_status': task.get('desiredStatus'),
                            'health_status': task.get('healthStatus', 'UNKNOWN'),
                            'containers': [
                                {
                                    'name': container['name'],
                                    'last_status': container.get('lastStatus'),
                                    'exit_code': container.get('exitCode'),
                                    'reason': container.get('reason', '')
                                }
                                for container in task.get('containers', [])
                            ],
                            'cpu': task.get('cpu'),
                            'memory': task.get('memory')
                        }
                except ClientError:
                    continue

            return None

        except ClientError as e:
            print(f"Error fetching ECS task health for {task_id}: {e}")
            return None

    def get_alb_target_health(self, load_balancer_name: str) -> Optional[Dict[str, Any]]:
        """Get ALB target group health status"""
        try:
            # Get load balancer
            lb_response = self.elbv2.describe_load_balancers(
                Names=[load_balancer_name.split('/')[-2]]  # Extract name from ARN format
            )

            if not lb_response['LoadBalancers']:
                return None

            lb_arn = lb_response['LoadBalancers'][0]['LoadBalancerArn']

            # Get target groups
            tg_response = self.elbv2.describe_target_groups(
                LoadBalancerArn=lb_arn
            )

            health_data = {
                'load_balancer': load_balancer_name,
                'state': lb_response['LoadBalancers'][0]['State']['Code'],
                'target_groups': []
            }

            for tg in tg_response.get('TargetGroups', []):
                tg_arn = tg['TargetGroupArn']

                # Get target health
                health_response = self.elbv2.describe_target_health(
                    TargetGroupArn=tg_arn
                )

                healthy_count = sum(
                    1 for t in health_response['TargetHealthDescriptions']
                    if t['TargetHealth']['State'] == 'healthy'
                )
                total_count = len(health_response['TargetHealthDescriptions'])

                health_data['target_groups'].append({
                    'name': tg['TargetGroupName'],
                    'healthy_targets': healthy_count,
                    'total_targets': total_count,
                    'targets': [
                        {
                            'id': t['Target']['Id'],
                            'port': t['Target'].get('Port'),
                            'state': t['TargetHealth']['State'],
                            'reason': t['TargetHealth'].get('Reason', '')
                        }
                        for t in health_response['TargetHealthDescriptions']
                    ]
                })

            return health_data

        except ClientError as e:
            print(f"Error fetching ALB health for {load_balancer_name}: {e}")
            return None

    def get_recent_cloudformation_changes(self, lookback_hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent CloudFormation stack changes/deployments"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)

            # List all stacks
            stacks_response = self.cloudformation.list_stacks(
                StackStatusFilter=[
                    'CREATE_COMPLETE', 'UPDATE_COMPLETE',
                    'UPDATE_ROLLBACK_COMPLETE', 'ROLLBACK_COMPLETE'
                ]
            )

            recent_changes = []

            for stack_summary in stacks_response.get('StackSummaries', []):
                last_updated = stack_summary.get('LastUpdatedTime') or stack_summary.get('CreationTime')

                if last_updated and last_updated.replace(tzinfo=None) > cutoff_time:
                    # Get stack events for details
                    events_response = self.cloudformation.describe_stack_events(
                        StackName=stack_summary['StackName']
                    )

                    recent_events = [
                        event for event in events_response.get('StackEvents', [])
                        if event['Timestamp'].replace(tzinfo=None) > cutoff_time
                    ]

                    if recent_events:
                        recent_changes.append({
                            'stack_name': stack_summary['StackName'],
                            'status': stack_summary['StackStatus'],
                            'last_updated': str(last_updated),
                            'recent_events_count': len(recent_events),
                            'failed_resources': [
                                {
                                    'resource': event['LogicalResourceId'],
                                    'status': event['ResourceStatus'],
                                    'reason': event.get('ResourceStatusReason', '')
                                }
                                for event in recent_events
                                if 'FAILED' in event['ResourceStatus']
                            ]
                        })

            return recent_changes

        except ClientError as e:
            print(f"Error fetching CloudFormation changes: {e}")
            return []

    def get_cloudwatch_metrics(
        self,
        log_group: str,
        lookback_minutes: int = 30
    ) -> Dict[str, Any]:
        """Get CloudWatch metrics for the service (CPU, memory, errors)"""
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=lookback_minutes)

            metrics = {
                'period': f'{lookback_minutes} minutes',
                'cpu': {},
                'memory': {},
                'errors': {}
            }

            # Determine namespace and dimensions based on log group
            namespace = None
            dimensions = []

            if '/lambda/' in log_group:
                namespace = 'AWS/Lambda'
                func_name = log_group.split('/')[-1]
                dimensions = [{'Name': 'FunctionName', 'Value': func_name}]

                # Lambda-specific metrics
                metric_queries = [
                    ('Errors', 'errors', 'Sum'),
                    ('Duration', 'duration', 'Average'),
                    ('ConcurrentExecutions', 'concurrency', 'Maximum')
                ]

            elif '/ecs/' in log_group:
                namespace = 'AWS/ECS'
                # Would need cluster/service name from context
                metric_queries = [
                    ('CPUUtilization', 'cpu', 'Average'),
                    ('MemoryUtilization', 'memory', 'Average')
                ]

            else:
                # Generic application metrics
                metric_queries = []

            # Fetch metrics
            for metric_name, key, stat in metric_queries:
                try:
                    response = self.cloudwatch.get_metric_statistics(
                        Namespace=namespace,
                        MetricName=metric_name,
                        Dimensions=dimensions,
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=300,  # 5-minute intervals
                        Statistics=[stat]
                    )

                    datapoints = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])

                    if datapoints:
                        metrics[key] = {
                            'current': datapoints[-1][stat],
                            'average': sum(d[stat] for d in datapoints) / len(datapoints),
                            'max': max(d[stat] for d in datapoints),
                            'datapoints': len(datapoints)
                        }

                except ClientError as e:
                    print(f"Error fetching metric {metric_name}: {e}")
                    continue

            return metrics

        except ClientError as e:
            print(f"Error fetching CloudWatch metrics: {e}")
            return {}

    def get_resource_tags(self, resource_id: str, resource_type: str) -> Dict[str, str]:
        """Get resource tags for additional context"""
        try:
            if resource_type == 'ec2':
                response = self.ec2.describe_tags(
                    Filters=[
                        {'Name': 'resource-id', 'Values': [resource_id]}
                    ]
                )

                return {
                    tag['Key']: tag['Value']
                    for tag in response.get('Tags', [])
                }

            elif resource_type == 'ecs':
                # ECS tags require ARN - would need full task ARN
                return {}

            return {}

        except ClientError as e:
            print(f"Error fetching resource tags: {e}")
            return {}

    def format_context_for_prompt(self, context: Dict[str, Any]) -> str:
        """Format gathered context into a human-readable string for AI prompt"""
        sections = []

        # Log Context Section
        if context.get('log_context'):
            lc = context['log_context']
            sections.append("## Infrastructure Context")
            sections.append(f"- Type: {lc.get('infrastructure_type', 'unknown')}")

            if lc.get('pod_name'):
                sections.append(f"- Pod: {lc['pod_name']}")
            if lc.get('node_name'):
                sections.append(f"- Node: {lc['node_name']}")
            if lc.get('task_id'):
                sections.append(f"- ECS Task: {lc['task_id']}")
            if lc.get('cluster_name'):
                sections.append(f"- Cluster: {lc['cluster_name']}")
            if lc.get('container_id'):
                sections.append(f"- Container: {lc['container_id'][:12]}")
            if lc.get('resource_id'):
                sections.append(f"- Resource ID: {lc['resource_id']}")

        # Recent Logs
        if context.get('recent_logs'):
            sections.append("\n## Recent Log Entries (last 10 minutes)")
            for log in context['recent_logs'][:10]:  # Show last 10
                timestamp = datetime.fromtimestamp(log['timestamp'] / 1000).strftime('%H:%M:%S')
                sections.append(f"[{timestamp}] {log['message'][:200]}")

        # Compute Health
        if context.get('compute'):
            if context['compute'].get('ec2'):
                ec2 = context['compute']['ec2']
                sections.append("\n## EC2 Instance Health")
                sections.append(f"- State: {ec2['instance_state']}")
                sections.append(f"- System Status: {ec2['system_status']}")
                sections.append(f"- Instance Status: {ec2['instance_status']}")
                if ec2.get('events'):
                    sections.append("- Events: " + ", ".join(e['code'] for e in ec2['events']))

            if context['compute'].get('ecs'):
                ecs = context['compute']['ecs']
                sections.append("\n## ECS Task Health")
                sections.append(f"- Last Status: {ecs['last_status']}")
                sections.append(f"- Desired Status: {ecs['desired_status']}")
                sections.append(f"- Health: {ecs['health_status']}")
                sections.append("- Containers:")
                for container in ecs.get('containers', []):
                    sections.append(f"  - {container['name']}: {container['last_status']}")
                    if container.get('exit_code'):
                        sections.append(f"    Exit code: {container['exit_code']}")

        # Load Balancer Health
        if context.get('load_balancers') and context['load_balancers']:
            lb = context['load_balancers']
            sections.append("\n## Load Balancer Health")
            sections.append(f"- State: {lb['state']}")
            for tg in lb.get('target_groups', []):
                sections.append(f"- {tg['name']}: {tg['healthy_targets']}/{tg['total_targets']} healthy")

        # Recent Changes
        if context.get('recent_changes'):
            sections.append("\n## Recent Infrastructure Changes (last 24h)")
            for change in context['recent_changes'][:5]:  # Show last 5
                sections.append(f"- {change['stack_name']}: {change['status']}")
                if change.get('failed_resources'):
                    for failed in change['failed_resources']:
                        sections.append(f"  ⚠️ {failed['resource']}: {failed['reason']}")

        # Metrics
        if context.get('metrics'):
            metrics = context['metrics']
            sections.append(f"\n## CloudWatch Metrics ({metrics.get('period', 'recent')})")

            if metrics.get('cpu'):
                cpu = metrics['cpu']
                sections.append(f"- CPU: current={cpu['current']:.1f}%, avg={cpu['average']:.1f}%, max={cpu['max']:.1f}%")

            if metrics.get('memory'):
                mem = metrics['memory']
                sections.append(f"- Memory: current={mem['current']:.1f}%, avg={mem['average']:.1f}%, max={mem['max']:.1f}%")

            if metrics.get('errors'):
                err = metrics['errors']
                sections.append(f"- Errors: current={err['current']}, total={err.get('max', 0)}")

        # Resource Tags
        if context.get('resource_tags'):
            sections.append("\n## Resource Tags")
            for key, value in context['resource_tags'].items():
                sections.append(f"- {key}: {value}")

        return "\n".join(sections)

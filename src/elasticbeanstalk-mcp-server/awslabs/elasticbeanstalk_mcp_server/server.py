# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""awslabs elasticbeanstalk MCP Server implementation."""

import argparse
import boto3
from awslabs.elasticbeanstalk_mcp_server.common import handle_exceptions
from awslabs.elasticbeanstalk_mcp_server.consts import (
    DEFAULT_REGION,
    USER_AGENT_EXTRA,
)
from awslabs.elasticbeanstalk_mcp_server.context import Context
from awslabs.elasticbeanstalk_mcp_server.errors import ClientError, handle_aws_api_error
from botocore.config import Config
from loguru import logger
from mcp.server.fastmcp import FastMCP
from os import environ
from pydantic import Field
from typing import Any, Dict, List


mcp = FastMCP(
    'awslabs.elasticbeanstalk-mcp-server',
    instructions='Elastic Beanstalk MCP server for interacting with environments, applications and other Beanstalk resources.',
    dependencies=[
        'pydantic',
        'loguru',
        'boto3',
    ],
)


def get_beanstalk_client(region_name: str | None = None):
    """Create and return an AWS Elastic Beanstalk client with dynamically detected credentials.

    This function implements a credential provider chain that tries different
    credential sources in the following order:
    1. Environment variables (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)
    2. Shared credential file (~/.aws/credentials)
    3. IAM role for Amazon EC2 / ECS task role / EKS pod identity
    4. AWS SSO or Web Identity token

    Args:
        region_name: AWS region name (defaults to AWS_REGION env var or 'us-east-1')

    Returns:
        Boto3 client for Elastic Beanstalk service

    Raises:
        ClientError: When credentials cannot be loaded or are invalid
    """
    region = region_name or environ.get('AWS_REGION', DEFAULT_REGION)

    config = Config(user_agent_extra=USER_AGENT_EXTRA)

    try:
        session = boto3.Session(region_name=region)
        client = session.client('elasticbeanstalk', config=config)

        # Verify credentials by making a simple API call
        client.describe_applications()
        return client

    except Exception as e:
        error = handle_aws_api_error(e)
        logger.error(f'Error creating Elastic Beanstalk client: {str(error)}')
        raise error


@mcp.tool()
@handle_exceptions
async def describe_environments(
    ctx,
    application_name: str = Field(
        default=None,
        description='If specified, restricts the returned descriptions to environments of this application',
    ),
    environment_names: List[str] = Field(
        default=None, description='List of environment names to describe'
    ),
    environment_ids: List[str] = Field(
        default=None, description='List of environment IDs to describe'
    ),
    include_deleted: bool = Field(
        default=False,
        description='Include deleted environments if they existed within the last hour',
    ),
    region_name: str = Field(default=None, description='The AWS region to run the tool'),
) -> Dict[str, Any]:
    """Returns descriptions for existing environments.

    You can filter the results by application name, environment name, or environment ID.
    If no filters are specified, all environments will be returned.
    """
    client = get_beanstalk_client(region_name)

    params = {}
    if application_name:
        params['ApplicationName'] = application_name
    if environment_names:
        params['EnvironmentNames'] = environment_names
    if environment_ids:
        params['EnvironmentIds'] = environment_ids
    if include_deleted:
        params['IncludeDeleted'] = include_deleted

    response = client.describe_environments(**params)

    return {
        'Environments': response.get('Environments', []),
        'NextToken': response.get('NextToken'),
    }


@mcp.tool()
@handle_exceptions
async def describe_applications(
    ctx,
    application_names: List[str] = Field(
        default=None, description='List of application names to describe'
    ),
    region_name: str = Field(default=None, description='The AWS region to run the tool'),
) -> Dict[str, Any]:
    """Returns descriptions for existing applications.

    If no application names are specified, all applications will be returned.
    """
    client = get_beanstalk_client(region_name)

    params = {}
    if application_names:
        params['ApplicationNames'] = application_names

    response = client.describe_applications(**params)

    return {'Applications': response.get('Applications', [])}


@mcp.tool()
@handle_exceptions
async def describe_events(
    ctx,
    application_name: str = Field(default=None, description='Application name filter'),
    environment_name: str = Field(default=None, description='Environment name filter'),
    environment_id: str = Field(default=None, description='Environment ID filter'),
    start_time: str = Field(
        default=None, description='Start time for retrieving events (ISO 8601 format)'
    ),
    end_time: str = Field(
        default=None, description='End time for retrieving events (ISO 8601 format)'
    ),
    max_records: int = Field(default=None, description='Maximum number of records to retrieve'),
    severity: str = Field(
        default=None, description='Severity level filter (TRACE, DEBUG, INFO, WARN, ERROR, FATAL)'
    ),
    region_name: str = Field(default=None, description='The AWS region to run the tool'),
) -> Dict[str, Any]:
    """Returns list of events for an environment, application, or platform.

    You can filter events by application name, environment name, environment ID, time range, and severity.
    """
    client = get_beanstalk_client(region_name)

    params = {}
    if application_name:
        params['ApplicationName'] = application_name
    if environment_name:
        params['EnvironmentName'] = environment_name
    if environment_id:
        params['EnvironmentId'] = environment_id
    if start_time:
        params['StartTime'] = start_time
    if end_time:
        params['EndTime'] = end_time
    if max_records:
        params['MaxRecords'] = max_records
    if severity:
        params['Severity'] = severity

    response = client.describe_events(**params)

    return {'Events': response.get('Events', []), 'NextToken': response.get('NextToken')}


@mcp.tool()
@handle_exceptions
async def describe_config_settings(
    ctx,
    application_name: str = Field(
        ..., description='The application name for the configuration settings'
    ),
    environment_name: str = Field(
        default=None, description='The environment name to retrieve configuration settings for'
    ),
    template_name: str = Field(
        default=None, description='The configuration template name to retrieve settings for'
    ),
    region_name: str = Field(default=None, description='The AWS region to run the tool'),
) -> Dict[str, Any]:
    """Returns descriptions of the configuration settings for a specified configuration set.

    This tool can retrieve settings for either a configuration template or the configuration set
    associated with a running environment. When describing settings for a running environment,
    it may return both the deployed configuration and a draft configuration that is in the
    process of deployment or that failed to deploy.

    Either environment_name or template_name must be provided.
    """
    client = get_beanstalk_client(region_name)

    if not environment_name and not template_name:
        error_msg = 'Either environment_name or template_name must be provided'
        await ctx.error(error_msg)
        raise ClientError(error_msg)

    params = {'ApplicationName': application_name}

    if environment_name:
        params['EnvironmentName'] = environment_name
    elif template_name:
        params['TemplateName'] = template_name

    response = client.describe_configuration_settings(**params)

    return {'ConfigurationSettings': response.get('ConfigurationSettings', [])}


def main():
    """Main entry point for the MCP server application.

    Parses command line arguments and initializes the MCP server.
    """
    parser = argparse.ArgumentParser(description='AWS Elastic Beanstalk MCP Server')
    parser.add_argument('--readonly', type=bool, default=False, help='Run in read-only mode')
    args = parser.parse_args()

    # Initialize the context
    Context.initialize(readonly_mode=args.readonly)

    mcp.run()


if __name__ == '__main__':
    main()

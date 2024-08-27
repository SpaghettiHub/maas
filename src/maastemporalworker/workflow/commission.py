# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from dataclasses import dataclass

from temporalio import workflow
from temporalio.common import RetryPolicy


@dataclass
class CommissionParam:
    system_id: str
    queue: str


@dataclass
class CommissionNParam:
    params: list[CommissionParam]


@workflow.defn(name="CommissionNWorkflow", sandboxed=False)
class CommissionNWorkflow:
    @workflow.run
    async def run(self, params: CommissionNParam) -> None:
        for param in params.params:
            await workflow.execute_child_workflow(
                "commission",
                param,
                id=f"commission:{param.system_id}",
                task_queue=param.queue,
                retry_policy=RetryPolicy(maximum_attempts=5),
            )

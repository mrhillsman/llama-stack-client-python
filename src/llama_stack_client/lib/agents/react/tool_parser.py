# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.

import json
import uuid
from typing import List, Optional, Union

from llama_stack_client.types.shared.completion_message import CompletionMessage
from llama_stack_client.types.shared.tool_call import ToolCall

from pydantic import BaseModel, ValidationError

from ..tool_parser import ToolParser


class Param(BaseModel):
    name: str
    value: Union[str, int, float, bool]


class Action(BaseModel):
    tool_name: str
    tool_params: List[Param]


class ReActOutput(BaseModel):
    thought: str
    action: Optional[Action]
    answer: Optional[str]


class ReActToolParser(ToolParser):
    def get_tool_calls(self, output_message: CompletionMessage) -> List[ToolCall]:
        """
        Parse ReAct-formatted responses and extract tool calls.
        
        Returns empty list if:
        - Response contains a final answer (task is complete)
        - Response is thinking-only (no action specified)
        - Response is malformed
        """
        tool_calls: List[ToolCall] = []
        response_text = str(output_message.content)
        
        try:
            react_output = ReActOutput.model_validate_json(response_text)
        except ValidationError as e:
            # Enhanced error logging for debugging ReAct responses
            print(f"ReAct parsing error: {e}")
            print(f"Response content: {response_text[:200]}...")
            return tool_calls

        # Validate ReAct structure
        if not self._validate_react_structure(react_output):
            return tool_calls

        # If final answer is provided, no tool calls needed
        if react_output.answer is not None:
            return tool_calls

        # If only thinking (no action), no tool calls needed
        if react_output.action is None:
            return tool_calls

        # Extract and validate tool call
        tool_call = self._extract_tool_call(react_output.action)
        if tool_call:
            tool_calls.append(tool_call)

        return tool_calls

    def _validate_react_structure(self, react_output: ReActOutput) -> bool:
        """
        Validate that the ReAct response follows proper structure.
        """
        # Must have a thought
        if not react_output.thought or not react_output.thought.strip():
            print("ReAct validation error: Missing or empty 'thought' field")
            return False

        # Should have either action OR answer, not both
        has_action = react_output.action is not None
        has_answer = react_output.answer is not None
        
        if has_action and has_answer:
            print("ReAct validation error: Cannot have both 'action' and 'answer' in same response")
            return False

        # If has action, validate action structure
        if has_action and react_output.action is not None:
            if not react_output.action.tool_name:
                print("ReAct validation error: Action missing tool_name")
                return False
            if not react_output.action.tool_params:
                print("ReAct validation error: Action missing tool_params")
                return False

        return True

    def _extract_tool_call(self, action: Action) -> Optional[ToolCall]:
        """
        Extract a ToolCall from a ReAct Action.
        """
        try:
            tool_name = action.tool_name
            tool_params = action.tool_params
            
            # Convert param list to dict
            params: dict[str, Union[str, float, bool, None]] = {}
            for param in tool_params:
                params[param.name] = param.value

            if not tool_name or not params:
                print(f"Incomplete tool call: tool_name={tool_name}, params={params}")
                return None

            call_id = str(uuid.uuid4())
            return ToolCall(
                call_id=call_id,
                tool_name=tool_name,
                arguments=params,
                arguments_json=json.dumps(params),
            )
            
        except Exception as e:
            print(f"Error extracting tool call: {e}")
            return None

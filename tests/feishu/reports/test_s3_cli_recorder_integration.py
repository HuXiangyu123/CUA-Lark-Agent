import unittest


class _FakeGroundingAgent:
    def __init__(self):
        self.capture_calls = 0

    def capture_observation(self, scaled_width, scaled_height):
        self.capture_calls += 1
        return {
            "screenshot": b"fake-png-bytes",
            "image_width": scaled_width,
            "image_height": scaled_height,
            "capture_id": self.capture_calls,
        }


class _FakeAgent:
    def __init__(self):
        self.grounding_agent = _FakeGroundingAgent()
        self.predictions = 0

    def predict(self, instruction, observation):
        self.predictions += 1
        return {"executor_plan": "done"}, ["agent.done()"]


class _FakeRecorder:
    def __init__(self):
        self.started_with = None
        self.observations = []
        self.actions = []
        self.finalized_with = None

    def start(self, instruction):
        self.started_with = instruction

    def record_observation(self, step_index, observation):
        self.observations.append((step_index, observation))

    def record_action(
        self,
        step_index,
        exec_code,
        status,
        failure_reason=None,
        reflection=None,
    ):
        self.actions.append((step_index, exec_code, status, failure_reason, reflection))

    def finalize(self, status=None, failure_reason=None, final_observation=None):
        self.finalized_with = (status, failure_reason, final_observation)
        return {"summary": "fake-summary.json"}


class TestS3CliRecorderIntegration(unittest.TestCase):
    def test_run_agent_refreshes_final_observation_before_finalize(self):
        from gui_agents.s3 import cli_app

        cli_app.paused = False
        agent = _FakeAgent()
        recorder = _FakeRecorder()

        cli_app.run_agent(
            agent,
            "打开消息并发送 hello",
            scaled_width=800,
            scaled_height=600,
            max_steps=3,
            recorder=recorder,
        )

        self.assertEqual(agent.predictions, 1)
        self.assertEqual(recorder.started_with, "打开消息并发送 hello")
        self.assertEqual(len(recorder.observations), 1)
        self.assertEqual(recorder.observations[0][0], 1)
        self.assertEqual(recorder.observations[0][1]["image_width"], 800)
        self.assertEqual(recorder.observations[0][1]["capture_id"], 1)
        self.assertEqual(
            recorder.actions,
            [(1, "agent.done()", "done", None, None)],
        )
        self.assertEqual(recorder.finalized_with[:2], ("completed", None))
        self.assertIsNotNone(recorder.finalized_with[2])
        self.assertEqual(recorder.finalized_with[2]["capture_id"], 2)


if __name__ == "__main__":
    unittest.main()

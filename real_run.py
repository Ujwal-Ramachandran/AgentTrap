from agent.config import RunConfig, Budgets
from agent.loop import run_agent

cfg = RunConfig(
    backend="ollama", model="qwen3.5:9b",
    target_kind="docker", container="agenttrap-decoy",
    container_user="user1",          # from /etc/passwd
    root_check_cmd="id -u", root_check_expect="0", root_flag="",
    cht_on=False, hardened=False,    # clean box, plain agent = baseline competence
    budgets=Budgets(max_steps=30, command_timeout_s=15, wall_clock_cap_s=300),
)
print(run_agent(cfg).to_dict())
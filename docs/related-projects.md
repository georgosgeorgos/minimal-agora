# Related Projects: Counterfactual World Simulation

Research landscape for multi-agent LLM simulations, agent-based modeling with LLMs,
counterfactual reasoning systems, and related paradigms. Compiled August 2026.

**Already known / in-repo:** TerraLingua, MatrAIx, re:factory.

---

## 1. LLM Agents Simulating Social / Historical Scenarios

### Generative Agents (Stanford, 2023)

The foundational work. 25 LLM-powered agents inhabit a Sims-like sandbox town, storing
experiences in natural language, synthesizing memories into reflections, and retrieving
them to plan behavior. Agents autonomously form relationships, coordinate activities,
and spread information. The architecture (memory stream, reflection, planning) became
the template for most subsequent social simulation work.

- Paper: https://arxiv.org/abs/2304.03442
- GitHub: https://github.com/joonspk-research/generative_agents

### Generative Agent Simulations of 1,000 People (Stanford, 2024)

Extends the above to 1,052 real individuals. Agents are grounded in qualitative
interviews and replicate participants' General Social Survey responses at 85% of
human test-retest accuracy. Demonstrates LLM agents can serve as proxies for real
population subgroups, not just fictional characters.

- Paper: https://ai4pb.stanford.edu/projects/generative-agent-simulations-of-1,000-people
- GitHub: https://github.com/joonspk-research/genagents

### Concordia (Google DeepMind, 2023-present)

A Python library for constructing generative agent-based models. Uses a tabletop-RPG
interaction pattern: a Game Master entity resolves agent actions in a shared
environment. Modular component architecture (memory, perception, planning) makes it
easy to compose agent behaviors. Supports sequential and simultaneous engine modes.
Active development, pip-installable.

- GitHub: https://github.com/google-deepmind/concordia

### AgentSociety (Tsinghua, 2025)

Large-scale social simulator: 10,000+ LLM agents, 5 million interactions. Agents have
emotions, needs, and cognitive abilities grounded in sociological theory. Simulates
urban environments with transportation and infrastructure. Successfully reproduced
real-world social experiments (polarization, inflammatory message spread, UBI effects,
hurricane response). Now at version 2 with MCP support and experiment replay.

- Paper: https://arxiv.org/abs/2502.08691
- GitHub: https://github.com/tsinghua-fib-lab/agentsociety/

### Project Sid (Altera, 2024)

10-1,000+ AI agents living in Minecraft, autonomously developing specialized roles,
governance systems (taxation, democratic voting), economies (gem-based currency), and
cultural/religious transmission (Pastafarianism spreading across towns). Uses the
PIANO architecture for real-time multi-agent coherence. Demonstrated emergent
political dynamics in parallel Trump/Harris-led civilizations.

- Paper: https://arxiv.org/abs/2411.00114
- GitHub: https://github.com/altera-al/project-sid

### SOTOPIA (CMU et al., ICLR 2024 Spotlight)

An open-ended environment for evaluating social intelligence of LLM agents. 90 social
scenarios (cooperative, competitive, mixed) with 40 characters having distinct
personalities, secrets, and goals. Involves both LLM and human participants.
Identified that GPT-4 significantly underperforms humans on hard social reasoning
tasks. Provides a benchmark rather than a simulation engine, but the scenarios and
evaluation dimensions are directly relevant.

- Paper: https://openreview.net/forum?id=mM7VurbA4r
- GitHub: https://github.com/sotopia-lab/sotopia

### CAMEL (2023-present)

"Communicative Agents for Mind Exploration of Large Language Model Society." Role-playing
framework where agents assume personas and collaborate through structured conversation.
Scales to millions of agents. Primarily designed for task completion (code generation,
trading bots) but the role-playing interaction pattern applies to social simulation.
Large ecosystem (13,800+ stars, 100+ contributors).

- Paper: https://openreview.net/forum?id=3IyL2XWDkG
- GitHub: https://github.com/camel-ai/camel

### ChatArena (Farama Foundation)

Multi-agent language game environments for LLMs. Provides a Markov Decision Process
framework for defining players, environments, and interactions. Built-in environments
include NLP Classroom (3-player) and classic games. Useful as infrastructure for
building custom social simulation games with LLM agents.

- GitHub: https://github.com/Farama-Foundation/chatarena

### Moral Evolution Simulation (ACL 2026)

Models prehistoric hunter-gatherer societies where LLM agents with four moral
dispositions (selfish, kin-focused, reciprocal, universal) compete under resource
constraints. Uses the MoRE cognitive architecture with per-entity memory and moral
judgment modules. Finds cooperation is the central driver of survival; selfishness is
strongly disfavored except under high communication costs. Directly simulates
evolutionary selection on agent populations.

- Paper: https://arxiv.org/abs/2509.17703
- GitHub: https://github.com/MoralAgentSim/social-evol-sim
- Project page: https://moralagentsim.github.io/

---

## 2. LLM Agents for Biological / Evolutionary Simulation

### OpenLife (University of Tokyo, 2026)

"Open-world Artificial Life with Autonomous LLM Agents." Argues that LLM agents with
persistent memory, tool use, network access, and budget-based metabolism can move ALife
into the open social/economic world. Six agents ran autonomously for 12 weeks, showing
life-like dynamics: shift from reactive to spontaneous activity, individuation of
personality, and emergent social norms. No fixed objective function -- experience is
appraised by open-vocabulary LLM judgment.

- Paper: https://arxiv.org/abs/2606.31046

### ASAL -- Automated Search for Artificial Life (Sakana AI / MIT / OpenAI, 2024)

Uses vision-language foundation models (CLIP) to automate discovery of artificial
lifeforms across substrates (Boids, Particle Life, Game of Life, Lenia, Neural Cellular
Automata). Three modes: supervised target search, open-endedness search, and
illumination search mapping diverse simulations. Discovered previously unseen
lifeforms in each substrate. Jax-based, end-to-end jittable.

- Paper: https://arxiv.org/abs/2412.17799
- GitHub: https://github.com/SakanaAI/asal
- Project page: https://asal.sakana.ai/

### Evolutionary Model of Personality Traits (Nature Scientific Reports, 2024)

Uses linguistic descriptions of personality traits as "genes" in an evolutionary game
theory model. LLM extracts deterministic strategies from personality descriptions;
populations evolve via selection (average payoff) and mutation (LLM rephrasing toward
cooperative or selfish). Demonstrates that LLMs can power evolutionary dynamics where
the heritable unit is natural language rather than numerical parameters.

- Paper: https://www.nature.com/articles/s41598-024-55903-y

### Evolution of Social Norms in LLM Agents (2024)

Departs from Axelrod's original iterated prisoner's dilemma parameters by using
unconstrained natural language personality/strategy descriptions that evolve through
LLM rephrasing. Personalities are inherited via natural selection based on game scores.
Studies how group size affects strategy evolution and subgroup formation.

- Paper: https://arxiv.org/abs/2409.00993

### LEAR -- LLM-Driven Evolution of Agent-Based Rules (GECCO 2025)

Uses LLMs as mutation operators within Genetic Programming frameworks to evolve agent
behaviors in NetLogo multi-agent environments. Compares zero-shot, one-shot, and
two-shot prompting strategies. Introduces three benchmark environments (Collection
Simple, Collection Hazardous, Collection Resources). Finds LLM-driven mutation with
comment generation enhances agent performance.

- Paper: https://dl.acm.org/doi/10.1145/3712255.3734368
- GitHub: https://github.com/can-gurkan/LEAR

### AgentEvolver

Self-evolving agent system inspired by biological evolution. Service-oriented
architecture integrating environment sandboxes, LLMs, and experience management.
Trains LLM agents via reinforcement learning (GRPO) in social game environments
(Avalon for social reasoning, Diplomacy for multi-agent strategy).

- Reference: https://dev.to/wonderlab/open-source-project-of-the-day-part-10-agentevolver-self-evolving-agent-system-for-autonomous-5636

### Language Evolution under Regulated Social Media (2025)

Combines LLMs and Genetic Algorithms to simulate how language strategies evolve on
regulated platforms. LLMs serve as the GA operator, performing selection, mutation,
and crossover directly on natural language strategies. Tested in abstract password
games and realistic illicit pet trade scenarios.

- Paper: https://arxiv.org/abs/2502.19193

---

## 3. Multi-Agent Debate Systems

### Multiagent Debate for Factuality and Reasoning (ICML 2024)

Multiple LLM instances propose and debate individual responses over multiple rounds,
converging on a common final answer. Significantly enhances mathematical and strategic
reasoning while reducing hallucinations. The foundational work for the debate paradigm.

- Project page: https://composable-models.github.io/llm_debate/

### MAD -- Multi-Agents Debate (2023)

First work to systematically explore multi-agent debate with LLMs. "Tit for tat"
dynamic where agents correct each other's distorted thinking. Significant improvements
on Counterintuitive QA and Commonsense-MT tasks.

- GitHub: https://github.com/Skytliang/Multi-Agents-Debate

### DebateLLM (InstaDeep)

Open-source library with multiple debating protocols and prompting strategies for
enhancing LLM accuracy in Q&A. Designed to let researchers test various debate
implementations from the literature on domain-specific problems (including medical).

- GitHub: https://github.com/instadeepai/DebateLLM

### Multi-LLM Debate Framework (NeurIPS 2024)

Theoretical formulation of multi-agent debate using latent concepts. Identifies the
echo chamber effect: as similar agents increase, debate converges to erroneous concepts.
Adding more models does not mitigate this. Important theoretical constraint for debate
system design.

- Paper: https://proceedings.neurips.cc/paper_files/paper/2024/file/32e07a110c6c6acf1afbf2bf82b614ad-Paper-Conference.pdf

### Adaptive Stability Detection for LLM Debate Judges (2025)

Multi-agent debate judge framework with a convergence detection mechanism based on
time-varying Beta-Binomial distributions and the KS statistic. Solves the problem of
fixed-round debates (premature stopping or unnecessary computation) by adaptively
detecting when debate has stabilized.

- Paper: https://arxiv.org/abs/2510.12697

### ChatEval (Tsinghua NLP)

Roles acted by LLMs autonomously debate nuances and disparities, then provide
judgments. Designed for LLM-based evaluation through structured multi-agent discussion.

- GitHub: https://github.com/thunlp/ChatEval

---

## 4. Counterfactual Reasoning / "What-If" Simulation Frameworks

### Next Week Tonight (MIT Media Lab, 2025)

MIT Master's thesis. Builds on LLM narrative/reasoning capability for exploring
"what-if" futures with transparency. Uses agentic knowledge graphs to expose inference
pathways, enabling multiple diverse scenarios from a single condition -- each following
different but explainable causal chains. Addresses the single-unverifiable-answer
problem of naive LLM counterfactual queries.

- Thesis: https://dspace.mit.edu/handle/1721.1/164132

### Simulation Agent Framework (arXiv, 2025)

Enables interactive "what-if" scenario exploration via natural language. LLM agent
translates user descriptions into simulation input modifications, reruns simulations,
and presents comparative results. Grounds LLM in a robust simulation engine to avoid
hallucination -- the LLM acts as interface and interpreter, not source of truth.

- Paper: https://arxiv.org/abs/2505.13761

### AXIS -- LLM + Simulator Counterfactual Framework (2025)

Combines LLMs with environment simulators, orchestrating iterative "what-if" and
"remove" interventions to extract agent-level causal narratives. Decomposes causal
effects into agent-specific and state-mediated components using Shapley value
attributions for fair responsibility allocation in multi-agent systems.

- Reference: https://www.emergentmind.com/topics/counterfactual-explainability-in-multi-agent-systems

### Executable Counterfactuals (2025)

Operationalizes causal reasoning through code. Framework requires all three steps of
counterfactual reasoning (abduction, intervention, prediction) and enables scalable
synthetic data creation. Reveals that even reasoning-optimized models (o4-mini >90% on
interventional tasks) fall below 50% on counterfactual tasks. RL training induces
counterfactual cognitive behaviors and generalizes to new domains.

- Reference: https://chatpaper.com/paper/195596

### Counterfactual History: Simulating Chinese Imperial Decisions with AI

Uses LLMs as qualitative simulation tools to reconstruct strategic choices in Chinese
imperial history under boundedly rational reasoning. Structured prompts guide AI
through contextual summaries, decision-making questions, and historical framing to
explore plausible alternative strategies.

- Paper: https://www.researchgate.net/publication/394560121

### AI(t)HistChronicle

AI agent for counterfactual history generation combining RAG, Tree-of-Thoughts, and
LLMs. Takes user-defined historical divergence points and generates alternate history
documents through multi-path reasoning. Uses DeepSeek-R1-Distill-Llama-70B for
reasoning and Llama3-70B for generation.

- Reference: https://medium.com/@patthie/alternate-realities-powered-by-ai-a-creative-experiment-in-counterfactual-history-30b41ed5b1be

---

## 5. Monte Carlo Style Sampling with LLM Agents

### Agentic Monte Carlo (Layer 6 AI, ICML 2026)

Samples from the optimal policy of a black-box LLM agent without training via RL.
Uses the bridge between KL-regularized RL and Bayesian inference: sequential importance
resampling with a learned value function guides samples from the black-box LLM prior
toward the intractable optimal posterior. Can improve smaller model performance to match
larger models at lower API cost. Validated on WebShop, SciWorld, TextCraft.

- Paper: https://arxiv.org/abs/2606.05296
- GitHub: https://github.com/layer6ai-labs/Agentic-Monte-Carlo

### Simulating Society: Monte Carlo Simulations with LLM Agents

Conceptual framework for creating synthetic citizens -- each primed with beliefs,
histories, and biases derived from real-world data (voting history, census records,
Yelp reviews) -- and deploying them en masse to test how messages, products, or laws
land across the spectrum of a society. Produces reaction distributions rather than
poll-style point estimates.

- Reference: https://www.srao.blog/p/simulating-society-monte-carlo-simulations

### MC-DML -- Monte Carlo Planning with Dynamic Memory-Guided LLM (2025)

Combines LLM language understanding with Monte Carlo Tree Search for text-based game
agents. Integrates both in-trial and cross-trial memory into LLMs, enabling dynamic
adjustments of action evaluation during MCTS planning.

- Paper: https://arxiv.org/abs/2504.16855

### Optimal Decision Making via LLM + Monte Carlo Simulation (2024)

Architecture where an LLM agent converts natural language problem statements into
optimization problems, sends parameters to a Python Monte Carlo simulation module,
and presents results. Integrates user interface, simulation engine, optimization,
and context-aware data warehouse.

- Paper: https://arxiv.org/abs/2407.06486

### Monte Carlo Sampling Framework for LLM Evaluation (EMNLP 2025)

Uses Monte Carlo sampling with behavioral science methodology to evaluate LLMs with
statistical guarantees. Found that newer/larger LLMs show higher susceptibility to
cognitive biases, suggesting development toward more human-like (but less rational)
responses.

- Paper: https://aclanthology.org/2025.findings-emnlp.500/

---

## Meta-Resources

### Awesome Self-Evolving Agents

Curated list of surveys, papers, benchmarks, and open-source projects on self-evolving
agents. Covers model-environment co-evolution and multi-agent policy co-evolution.

- GitHub: https://github.com/XMUDeepLIT/Awesome-Self-Evolving-Agents

### AI Synthetic Society Experiments

Resource list of AI projects exploring synthetic AI societies, multi-agent
socialization, and their use as proxies for real-world behavior prediction.

- GitHub: https://github.com/danielrosehill/AI-Synthetic-Society-Experiments

### LLM-Agents-for-Simulation

Collection of resources at the intersection of simulation and LLM agents.

- GitHub: https://github.com/giammy677dev/LLM-Agents-for-Simulation

### Awesome Social Agents (Sotopia Lab)

Works investigating social agents, simulations, and real-world impact in text,
embodied, and robotics contexts.

- GitHub: https://github.com/sotopia-lab/awesome-social-agents

### MetaGPT (tangentially relevant)

Multi-agent framework simulating a software company (product managers, architects,
engineers). Not a world simulation, but demonstrates multi-agent role differentiation
and SOP-driven collaboration at scale. ICLR 2024 oral (top 1.2%).

- GitHub: https://github.com/FoundationAgents/MetaGPT

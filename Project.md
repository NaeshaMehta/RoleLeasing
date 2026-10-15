Decentralized Role-Leasing IoT Protocol Project Spec Sheet
Contents
1. Tech Stack	2
2. Network Configuration	2
3. Core Protocol Flows	3
3.1 Initialization	3
3.2 Capability Calculation	3
3.3 Capability Aggregation (Recursive)	3
3.4 Role Selection & Leasing	4
3.5 Migration Cost	4
3.6 Hysteresis	4
3.7 Epoch Fencing	4
3.8 Steady-State Operation	4
3.9 Failure Detection & Recovery	4
4. Network Events	5
5. Data Plane	5
6. Baselines for Comparison	5
7. Key Metrics to Measure	6
Primary Metrics	6
Secondary Metrics	6
Migration Record	6
8. Required Experiments	6
Experiment 1: Normal Operation	6
Experiment 2: Node Failures	6
Experiment 3: Energy Degradation	6
Experiment 4: Link Degradation	7
9. Architecture Layers	7
10. Two Planes	7
Control Plane	7
Data Plane	7
11. Target Outcome	7


In conventional agricultural IoT deployments, a centralized controller or gateway typically manages functions such as gateway coordination, anomaly detection, health monitoring, and device discoverability. As field size increases, however, centralized processing can introduce communication overhead, single points of failure, and slower adaptation when connectivity or node conditions change. The proposed protocol distributes these responsibilities across the hierarchy, allowing each role to be handled locally: Gateway nodes coordinate communication for their local field region, Anomaly Detection nodes identify abnormal sensor or environmental readings close to their source, Health Monitoring nodes track the operational condition and energy state of nearby devices, and Discoverability nodes maintain local awareness of available devices and capabilities. This reduces dependence on a central controller while allowing roles to shift as conditions change, making the network more suitable for large, distributed, and solar-powered agricultural IoT deployments.
A decentralized multi-hop IoT protocol for agricultural sensor networks where nodes recursively aggregate capabilities from their children and use those aggregated values to make temporary, cost-aware role assignments across hierarchical levels (Node → Subnet → Network → Internetwork).
The core mechanism is that the same role semantics work at every hierarchy level: a subnet can act as a "gateway" just like an individual node, but its capability is computed by aggregating the capabilities of its members.
The physical topology and logical hierarchy are assumed to be established before protocol execution. V1 focuses on dynamic capability evaluation, recursive aggregation, role selection, leasing, and adaptation to changing network conditions.
1. Tech Stack
•	Language: Python 3
•	Libraries: Mesa (agent library), transitions (state management library), SimPy (event simulation), NumPy/Pandas (metrics), Matplotlib (plots)	
•	Network model: Abstract undirected multi-hop graph
•	Runtime: Local Python execution; outputs CSV metrics + key plots
•	Hierarchy: Static logical hierarchy independent of physical mesh topology
2. Network Configuration
•	Nodes: 100
•	Subnets: 10
•	Networks: 3
•	Internetworks: 1

Internetwork
    
Networks
    
Subnets
    
Nodes

The hierarchy is predefined for each simulation run.
Physical topology and logical organization are separate:
Physical topology: NetworkX graph
Logical organization: Node → Subnet → Network → Internetwork
3. Core Protocol Flows
3.1 Initialization
1.	Generate a connected multi-hop mesh topology.
2.	Initialize each node with node ID, energy, health, link quality, centrality, and subnet membership.
3.	Create the predefined Node → Subnet → Network → Internetwork hierarchy.
4.	Calculate local capability C(node, role) for every supported role.
5.	Recursively aggregate capabilities through the hierarchy.
6.	Perform initial role assignment and create leases.

3.2 Capability Calculation
Each entity maintains a capability value for every supported role:
C(e,r) ∈ [0,1]
For nodes:
C(e,r) = wE × Energy + wH × Health + wQ × LinkQuality + wC × Centrality
•	Gateway: energy + link quality + centrality
•	Anomaly Detection: energy + health
•	Health Monitoring: energy + health
•	Discoverability: energy + link quality + health
All capability values are normalized to [0,1].

3.3 Capability Aggregation (Recursive)
Subnet:
C_subnet,r = Σ(w_i × C_child_i,r)
Network:
C_network,r = Σ(w_i × C_subnet_i,r)
Internetwork:
C_internetwork,r = Σ(w_i × C_network_i,r)
•	Deterministic
•	Normalized
•	Based only on child capability vectors
•	Free of hidden state
3.4 Role Selection & Leasing
Utility:
U(e,r) = C(e,r) − λ × MigrationCost(e,r)
For initial assignment:
U(e,r) = C(e,r)
Migration is permitted only when:
U_new > U_current + Δ
A selected candidate receives a temporary lease:
LEASE(role, holder, scope, epoch, start_time, expiry_time)
Adaptive lease duration:
T_lease = T_min + C(holder,r) × (T_max − T_min)
The holder attempts renewal at approximately 70% of the lease duration.
3.5 Migration Cost
MigrationCost = α × ControlMessages + β × StateTransfer + γ × EnergyCost + δ × Disruption
The cost model is deterministic and configurable. 
3.6 Hysteresis
Hysteresis prevents unnecessary role switching:
U(new) > U(current) + del
This allows measurement of the trade-off between role stability, adaptation, migration overhead, and energy consumption.
3.7 Epoch Fencing
Gateway / Subnet 4 / Epoch 7

Epoch 7 → Epoch 8
An old lease belonging to a previous epoch is invalid.
At most one active holder per (role, scope, epoch)
No distributed consensus protocol is simulated.
3.8 Steady-State Operation
Current simulation does not simulate individual control packets. Protocol operations instead produce abstract communication costs.
Capability update → control_messages += cost
Lease renewal → control_messages += cost
Role migration → control_messages += migration_cost
Role reassignment → control_messages += reassignment_cost
3.9 Failure Detection & Recovery
Failures are injected directly by the simulation:
fail_node(node_id)
Recovery flow:
Node failure
    ↓
Lease becomes invalid
    ↓
Candidate evaluation
    ↓
Utility calculation
    ↓
Hysteresis check
    ↓
New lease
Recovery time:
RecoveryTime = reassignment_time − failure_time
An optional fixed detection delay may be configured. No HELLO timeout or heartbeat protocol is required.
4. Network Events
•	Node failure: Node becomes unavailable → current lease becomes invalid → reassignment
•	Energy degradation: Energy decreases → capability decreases → possible migration
•	Link degradation: Link quality decreases → capability decreases → possible migration
•	Node recovery: Previously inactive node becomes available again and becomes a candidate
Node joining is treated as a state-change event rather than a discovery protocol.
5. Data Plane
The data plane is abstracted. Sensor traffic is represented using load counters:
Node load
Gateway load
Role placement affects the distribution of load.
6. Baselines for Comparison
Protocol	Mechanism
Static	Roles assigned once; no reassignment
Conventional Dynamic	Highest-capability candidate selected; immediate reassignment; no migration cost or hysteresis
Current Protocol	Recursive aggregation + capability assignment + migration cost + hysteresis + temporary adaptive leases
All three protocols use identical initial topology, initial node states, random seed, and event schedule.
7. Key Metrics to Measure
Primary Metrics
•	Network lifetime
•	Role migrations
•	Control messages
•	Average remaining energy
•	Role recovery time
•	Failed/unavailable roles
Secondary Metrics
•	Gateway load distribution
•	Energy variance
•	Active node count
•	Role availability
Migration Record
time
role
scope
old_holder
new_holder
old_capability
new_capability
migration_cost
old_utility
new_utility
8. Required Experiments
Experiment 1: Normal Operation
•	Energy consumption
•	Role stability
•	Control overhead
Experiment 2: Node Failures
•	Recovery time
•	Role availability
•	Role migrations
•	Control overhead
Experiment 3: Energy Degradation
•	Role migration
•	Energy distribution
•	Network lifetime
•	Migration overhead
Experiment 4: Link Degradation
•	Role migration
•	Recovery
•	Control overhead
9. Architecture Layers
Layer	Purpose
Physical Mesh	Abstract NetworkX undirected graph representing multi-hop connectivity
Capability Layer	Local capability vectors C(e,r) and recursive aggregation
Hierarchy Layer	Static Node → Subnet → Network → Internetwork structure
Role / Lease Layer	Utility, migration cost, hysteresis, role selection, leases, epoch fencing, migration
Event / Metrics Layer	Failures, energy/link changes, recovery, measurement
10. Two Planes
Control Plane
Abstractly simulated through operation/message costs:
CAP_UPDATE
LEASE_GRANT
LEASE_RENEW
LEASE_EXPIRE
MIGRATE
ROLE_REASSIGN
Actual network messages are not implemented.
Data Plane
Abstract sensor traffic represented by node and gateway load counters.
11. Target Outcome
Demonstrate that:
A node, subnet, or network can expose an aggregated capability for a role, allowing a parent entity to select and temporarily lease that role while accounting for migration cost and hysteresis as network conditions change. 

Primary experimental comparison:
Static assignment
        vs
Conventional dynamic assignment
        vs
Proposed recursive cost-aware role leasing

Should therefore focus on the measurable behavior of the capability → aggregation → selection → cost → hysteresis → lease → migration mechanism rather than on simulating the underlying network formation process.

12. Prior Art


Yes. That actually makes the architecture much cleaner. Mesa should handle the agent-based simulation/world, while transitions handles the protocol state machines. We can avoid building our own event/state framework.
Revised stack
Python
├── Mesa
│   ├── Model
│   ├── Nodes / Subnets / Networks
│   ├── Scheduler
│   ├── Network topology
│   └── Data collection
│
├── transitions
│   ├── Node states
│   ├── Lease lifecycle
│   ├── Role migration
│   └── Failure/recovery states
│
├── NetworkX
│   └── Physical mesh
│
├── NumPy
│   └── Capability / utility calculations
│
├── Pandas
│   └── Results
│
└── Matplotlib
    └── Experiments
The original spec already separates the physical mesh from the logical Node → Subnet → Network → Internetwork hierarchy, which fits Mesa particularly well.
Architecture I'd use
Instead of having 15+ independent modules, make the simulation revolve around three objects:
                    ┌─────────────────────┐
                    │     RoleModel       │
                    │      (Mesa)         │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              ↓                ↓                ↓
          NodeAgent        SubnetAgent      NetworkAgent
              │                │                │
              └────────────────┼────────────────┘
                               ↓
                    Protocol State Machine
                       (transitions)
NodeAgent
A Mesa agent containing:
class NodeAgent:
    energy
    health
    link_quality
    centrality

    capabilities
    roles
    leases

    state_machine
The node doesn't need to manually implement complicated event handling.
1. Mesa handles the world
Mesa becomes responsible for:
Simulation time
       ↓
Agent activation
       ↓
Node state changes
       ↓
Network conditions
       ↓
Data collection
So instead of writing:
while time < simulation_time:
    ...
we let Mesa drive the model.
For example:
class RoleLeasingModel(mesa.Model):

    def __init__(self, ...):
        self.nodes = ...
        self.topology = ...
        self.running = True

    def step(self):
        self.agents.shuffle_do("step")
This also gives us Mesa's data collection facilities rather than building our own metrics infrastructure from scratch.
2. transitions handles protocol state
This is where I think we'll get the biggest reduction in complexity.
A node/role can have states such as:
                 ┌───────────┐
                 │ AVAILABLE │
                 └─────┬─────┘
                       │ assign
                       ↓
                 ┌───────────┐
                 │   ACTIVE  │
                 └─────┬─────┘
                       │ renew
                       │
                       ├──────────────┐
                       │              │
                       ↓              ↓
                 ┌───────────┐  ┌────────────┐
                 │  RENEWED  │  │ MIGRATING  │
                 └───────────┘  └──────┬─────┘
                                       │
                                       ↓
                                  ┌──────────┐
                                  │  ACTIVE  │
                                  └──────────┘
And failure:
ACTIVE
  │
  │ failure / lease expiry
  ↓
INVALID
  │
  │ evaluate candidates
  ↓
MIGRATING
  │
  │ new lease
  ↓
ACTIVE
The spec already defines essentially this recovery lifecycle.
So transitions gives us:
states
triggers
guards
callbacks
transitions
conditions
without us writing a custom state engine.
3. Separate protocol logic from simulation logic
This is the important design decision.
Mesa asks:
What is happening to the simulated world?
Protocol asks:
What should the role-leasing mechanism do about it?
For example:
Mesa
 │
 ├── Node 17 energy drops
 │
 ↓
Protocol
 │
 ├── recompute capability
 ├── recompute utility
 ├── hysteresis check
 └── decide whether migration occurs
That makes experiments very easy to configure.
4. Capability engine can stay extremely small
We don't need a giant abstraction here.
def capability(node, role):
    if role == "gateway":
        return weighted(
            node.energy,
            node.link_quality,
            node.centrality
        )

    if role == "anomaly":
        return weighted(
            node.energy,
            node.health
        )

    if role == "health":
        return weighted(
            node.energy,
            node.health
        )

    if role == "discoverability":
        return weighted(
            node.energy,
            node.link_quality,
            node.health
        )
That directly follows the role-specific capability definitions in the spec.
Then aggregation is just:
def aggregate(children, role):
    return sum(
        weight(child) * child.capability[role]
        for child in children
    )
5. Role selection stays deterministic
We can keep the actual protocol almost embarrassingly simple:
def utility(candidate, role):
    return (
        candidate.capability[role]
        - LAMBDA * migration_cost(candidate, role)
    )
Then:
best = max(candidates, key=lambda x: utility(x, role))

if utility(best, role) > utility(current, role) + HYSTERESIS:
    migrate(current, best, role)
That is the core of the proposed mechanism: capability → utility → migration cost → hysteresis → lease.
6. Leases become a state machine
I'd make the lease itself a lightweight object:
class Lease:
    role
    holder
    scope
    epoch
    start
    expiry
And use transitions for its lifecycle:
PENDING
   ↓
ACTIVE
   ↓
RENEWING
   ↓
ACTIVE

ACTIVE
   ↓
EXPIRED

ACTIVE
   ↓
MIGRATING
   ↓
ACTIVE
Epoch fencing can simply be:
if lease.epoch != current_epoch:
    invalidate()
The spec explicitly requires old-epoch leases to become invalid.
7. Mesa hierarchy
I'd not make Subnet, Network and Internetwork Mesa agents unless we actually need them to act independently.
Instead:
class NodeAgent(mesa.Agent):
    ...

class Subnet:
    nodes = [...]

class Network:
    subnets = [...]

class Internetwork:
    networks = [...]
So:
Mesa Agent
    ↓
NodeAgent × 100
    ↓
Subnet objects × 10
    ↓
Network objects × 3
    ↓
Internetwork object × 1
This is simpler because the hierarchy in V1 is primarily for recursive capability aggregation, not independent behavior. The spec explicitly says the logical hierarchy is predefined and V1 focuses on dynamic capability evaluation and role assignment.
8. Events become Mesa model events
We can represent events simply:
model.fail_node(17)

model.degrade_energy(
    node=42,
    amount=0.2
)

model.degrade_link(
    node=31,
    amount=0.3
)
Then the protocol reacts.
For example:
Mesa event
    ↓
Node state changes
    ↓
Capability update
    ↓
Parent aggregation
    ↓
Role evaluation
    ↓
transitions trigger
    ↓
Lease migration
No custom event bus needed.
9. Experiments become configurations
This is where the architecture becomes really nice.
Instead of writing a completely different simulator for each experiment:
Experiment(
    protocol="proposed",
    failure_rate=0.10,
    energy_degradation=0.0,
    link_degradation=0.0,
    seed=42
)
Then:
                    Same Mesa Model
                          │
             ┌────────────┼────────────┐
             ↓            ↓            ↓
          Static      Dynamic       Proposed
             │            │            │
             └────────────┼────────────┘
                          ↓
                     DataCollector
                          ↓
                         CSV
The spec specifically requires identical topology, initial state, random seed and event schedule across the three protocols, so this configuration-driven approach will help enforce that.
Revised implementation roadmap
With Mesa + transitions, I'd shrink the earlier roadmap to:
M1 — Mesa skeleton
RoleLeasingModel
100 NodeAgents
NetworkX topology
static hierarchy
Mesa DataCollector
M2 — Node capabilities
energy
health
link quality
centrality
four role capability functions
M3 — Recursive hierarchy
Node → Subnet
Subnet → Network
Network → Internetwork
capability aggregation
M4 — Role allocator
candidate selection
utility
migration cost
hysteresis
M5 — transitions
role states
lease states
migration states
failure/recovery states
epoch fencing
M6 — Dynamic events
node failure
energy degradation
link degradation
recovery
M7 — Baselines
Static
Conventional Dynamic
Proposed
M8 — Experiments
normal operation
failures
energy degradation
link degradation
M9 — Analysis
migrations
control overhead
energy
lifetime
recovery
role availability
M10 — Ablation
no hysteresis
no migration cost
no adaptive leases
potentially no recursive aggregation
One architectural change I'd make
I would not overuse transitions.
Use it for things that genuinely have lifecycle/state:
Lease
Role assignment
Migration
Node operational state
Don't turn:
calculate_capability()
aggregate_capabilities()
calculate_utility()
into state machines. Those are deterministic functions.
So the final mental model is:
             ┌───────────────────────────────┐
             │          MESA MODEL           │
             │                               │
             │  Time / Agents / Events       │
             │  Network / Data Collection    │
             └───────────────┬───────────────┘
                             │
                     Node state changes
                             │
                             ▼
             ┌───────────────────────────────┐
             │       PROTOCOL ENGINE         │
             │                               │
             │ Capability                    │
             │ Recursive Aggregation          │
             │ Utility                       │
             │ Migration Cost                │
             │ Hysteresis                   │
             └───────────────┬───────────────┘
                             │
                             ▼
             ┌───────────────────────────────┐
             │        TRANSITIONS            │
             │                               │
             │ AVAILABLE → ACTIVE             │
             │ ACTIVE → RENEWING              │
             │ ACTIVE → MIGRATING             │
             │ ACTIVE → FAILED                │
             │ MIGRATING → ACTIVE             │
             └───────────────────────────────┘
That should make the implementation considerably smaller while keeping the protocol itself explicit and inspectable, which is exactly what we want for this project.


excluding networksX, determine how much of the project is implemented and how much is left

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import List, Tuple

class NetworkPlacer:
    """
    Deterministically places Networks, Subnets, and Nodes in 2D space.
    Ensures hierarchical clustering: Nodes -> Subnet -> Network.
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)

    def generate_map(
        self,
        num_networks: int,
        num_subnets_per_network: int,
        nodes_per_subnet: int,
        node_comm_range: float,
        world_size: Tuple[float, float] = (100.0, 100.0)
    ) -> pd.DataFrame:
        """
        Generates a deterministic map of networks, subnets, and nodes.

        Args:
            num_networks: Number of top-level networks.
            num_subnets_per_network: Number of subnets within each network.
            nodes_per_subnet: Number of nodes within each subnet.
            node_comm_range: Maximum communication distance between connected nodes.
                             Used to determine cluster tightness.
            world_size: (width, height) of the simulation area.

        Returns:
            DataFrame with columns: NetworkNo, SubnetNo, NodeNo, X, Y
        """

        rows = []
        node_counter_global = 0

        # 1. Place Network Centers globally
        # We use a grid-like distribution to ensure networks are distinct and not overlapping
        net_centers = self._place_network_centers(
            count=num_networks,
            world_size=world_size
        )

        for net_idx in range(num_networks):
            net_center_x, net_center_y = net_centers[net_idx]

            # 2. Place Subnet Centers relative to the Network Center
            # Subnets are clustered within a radius of the network center
            subnet_radius = node_comm_range * 5.0 # Adjust based on desired spread
            subnet_centers = self._place_cluster_points(
                count=num_subnets_per_network,
                center=(net_center_x, net_center_y),
                radius=subnet_radius,
                min_dist=node_comm_range * 2.0 # Ensure subnets don't overlap too much
            )

            for subnet_idx in range(num_subnets_per_network):
                sub_center_x, sub_center_y = subnet_centers[subnet_idx]

                # 3. Place Nodes relative to the Subnet Center
                # Nodes are clustered tightly within a radius of the subnet center
                node_radius = node_comm_range * 0.8 # Keep nodes close enough to talk

                node_positions = self._place_cluster_points(
                    count=nodes_per_subnet,
                    center=(sub_center_x, sub_center_y),
                    radius=node_radius,
                    min_dist=node_comm_range * 0.1 # Allow some overlap but keep distinct
                )

                for node_idx in range(nodes_per_subnet):
                    x, y = node_positions[node_idx]

                    rows.append({
                        "NetworkNo": net_idx + 1,
                        "SubnetNo": subnet_idx + 1,
                        "NodeNo": node_counter_global, # Global unique ID
                        "LocalNodeID": node_idx,       # ID within subnet
                        "X": x,
                        "Y": y
                    })
                    node_counter_global += 1

        df = pd.DataFrame(rows)

        # Optional: Visualize
        self._plot_map(df, world_size)

        return df

    def _place_network_centers(
        self,
        count: int,
        world_size: Tuple[float, float]
    ) -> List[Tuple[float, float]]:
        """
        Places network centers in a grid pattern to ensure they are distinct.
        """
        width, height = world_size

        # Calculate grid dimensions
        cols = int(np.ceil(np.sqrt(count)))
        rows = int(np.ceil(count / cols))

        cell_w = width / cols
        cell_h = height / rows

        centers = []
        for i in range(count):
            r = i // cols
            c = i % cols

            # Place at center of grid cell with slight jitter
            x = (c + 0.5) * cell_w + self.rng.uniform(-cell_w*0.1, cell_w*0.1)
            y = (r + 0.5) * cell_h + self.rng.uniform(-cell_h*0.1, cell_h*0.1)

            # Clamp to world bounds
            x = np.clip(x, 0, width)
            y = np.clip(y, 0, height)

            centers.append((x, y))

        return centers

    def _place_cluster_points(
        self,
        count: int,
        center: Tuple[float, float],
        radius: float,
        min_dist: float
    ) -> List[Tuple[float, float]]:
        """
        Places 'count' points in a circular cluster around 'center'.
        Uses rejection sampling to ensure minimum distance between points.
        If rejection fails, falls back to uniform random placement within radius.
        """
        cx, cy = center
        points = []

        for _ in range(count):
            placed = False
            attempts = 0
            max_attempts = count * 50 # Safety limit

            while not placed and attempts < max_attempts:
                # Generate random point within circle
                r = self.rng.uniform(0, radius)
                theta = self.rng.uniform(0, 2 * np.pi)

                x = cx + r * np.cos(theta)
                y = cy + r * np.sin(theta)

                # Check distance to existing points in this cluster
                valid = True
                for px, py in points:
                    dist_sq = (x - px)**2 + (y - py)**2
                    if dist_sq < min_dist**2:
                        valid = False
                        break

                if valid:
                    points.append((x, y))
                    placed = True
                attempts += 1

            # Fallback: If we can't find a spot with min_dist, just place it randomly
            # This ensures we always get 'count' nodes, even if they are very dense
            if not placed:
                r = self.rng.uniform(0, radius)
                theta = self.rng.uniform(0, 2 * np.pi)
                x = cx + r * np.cos(theta)
                y = cy + r * np.sin(theta)
                points.append((x, y))

        return points

    def _plot_map(self, df: pd.DataFrame, world_size: Tuple[float, float]):
        """Plots the generated map."""
        plt.figure(figsize=(12, 8))

        # Color by Network
        unique_networks = df['NetworkNo'].unique()
        colors = plt.cm.tab10(np.linspace(0, 1, len(unique_networks)))

        for i, net_id in enumerate(unique_networks):
            subset = df[df['NetworkNo'] == net_id]
            plt.scatter(subset['X'], subset['Y'], c=[colors[i]], label=f'Net {net_id}', s=50, alpha=0.7)

        # Draw connections within subnets to visualize density (optional but helpful for verification)
        # We only draw lines if nodes are close enough in the plot view

        plt.title("Generated Network Map")
        plt.xlabel("X")
        plt.ylabel("Y")
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.axis('equal')

        # Set limits slightly larger than world size for padding
        margin = 10
        plt.xlim(-margin, world_size[0] + margin)
        plt.ylim(-margin, world_size[1] + margin)

        plt.tight_layout()
        plt.show()

# --- Usage Example ---
if __name__ == "__main__":
    # Parameters
    SEED = 42
    NUM_NETWORKS = 3
    SUBNETS_PER_NET = 5
    NODES_PER_SUBNET = 10
    COMM_RANGE = 5.0

    placer = NetworkPlacer(seed=SEED)

    df_map = placer.generate_map(
        num_networks=NUM_NETWORKS,
        num_subnets_per_network=SUBNETS_PER_NET,
        nodes_per_subnet=NODES_PER_SUBNET,
        node_comm_range=COMM_RANGE,
        world_size=(75.0, 75.0)
    )

    # Save to CSV
    output_file = "network_map.csv"
    df_map.to_csv(output_file, index=False)
    print(f"Map saved to {output_file}")
    print(df_map.head())

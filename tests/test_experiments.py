import tempfile
import unittest
from pathlib import Path

import pandas as pd

from simulation.config import PROTOCOLS, SCENARIOS, SimulationConfig
from simulation.experiments import run_experiment_matrix
from simulation.protocols import MIGRATION_RECORD_COLUMNS


class TestExperimentMatrix(unittest.TestCase):
    def test_all_scenarios_protocols_export_required_artifacts(self):
        config = SimulationConfig(
            seed=9,
            subnet_counts=(1,),
            nodes_per_subnet=4,
            steps=2,
            epoch_length=10,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            summary = run_experiment_matrix(config, output_dir)

            self.assertEqual(len(summary), len(SCENARIOS) * len(PROTOCOLS))
            self.assertEqual(
                set(summary["protocol"]),
                set(PROTOCOLS),
            )
            self.assertEqual(
                set(summary["scenario"]),
                set(SCENARIOS),
            )
            self.assertTrue((output_dir / "summary.csv").is_file())
            self.assertTrue((output_dir / "summary_comparison.png").is_file())
            for scenario in SCENARIOS:
                self.assertTrue((output_dir / f"{scenario}_timeseries.png").is_file())
                for protocol in PROTOCOLS:
                    stem = f"{scenario}_{protocol}"
                    timeseries_path = output_dir / "timeseries" / f"{stem}_timeseries.csv"
                    migration_path = output_dir / "migrations" / f"{stem}_migrations.csv"
                    gateway_path = output_dir / "gateway_loads" / f"{stem}_gateway_loads.csv"
                    self.assertTrue(timeseries_path.is_file())
                    self.assertTrue(migration_path.is_file())
                    self.assertTrue(gateway_path.is_file())
                    timeseries = pd.read_csv(timeseries_path)
                    self.assertEqual(len(timeseries), config.steps + 1)
                    self.assertIn("role_availability", timeseries.columns)
                    migrations = pd.read_csv(migration_path)
                    self.assertTrue(set(MIGRATION_RECORD_COLUMNS).issubset(migrations.columns))
                    if not migrations.empty:
                        self.assertEqual(migrations["scenario"].drop_duplicates().tolist(), [scenario])


if __name__ == "__main__":
    unittest.main()

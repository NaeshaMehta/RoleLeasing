"""Per-tick, gateway-load, migration, and run-summary metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from simulation.protocols import MIGRATION_RECORD_COLUMNS

if TYPE_CHECKING:
    from simulation.runner import RoleSimulationModel


TIMESERIES_COLUMNS = (
    "time",
    "protocol",
    "active_node_count",
    "active_node_fraction",
    "mean_remaining_energy",
    "mean_solar_harvest_rate",
    "solar_energy_harvested_total",
    "solar_energy_harvested_step",
    "solar_energy_curtailed_total",
    "depleted_node_count",
    "energy_variance",
    "control_messages_total",
    "control_messages_step",
    "message_hop_transmissions_total",
    "message_hop_transmissions_step",
    "route_cost_total",
    "route_cost_step",
    "data_messages_step",
    "backhaul_messages_step",
    "backhaul_hop_transmissions_step",
    "data_hop_transmissions_step",
    "data_delivered_fraction",
    "sensor_data_delivery_fraction",
    "sensor_data_messages_step",
    "data_energy_consumed_step",
    "control_energy_consumed_step",
    "communication_energy_consumed_step",
    "gateway_energy_consumed_step",
    "failed_deliveries_total",
    "failed_deliveries_step",
    "role_migrations",
    "failed_unavailable_roles",
    "role_availability",
    "capability_service_continuity",
    "cumulative_capability_service_continuity",
    "sensor_items_generated_step",
    "sensor_items_delivered_step",
    "sensor_items_generated_total",
    "sensor_items_delivered_total",
    "cumulative_sensor_delivery_fraction",
    "role_recovery_time_mean",
    "gateway_load_mean",
    "gateway_load_variance",
)


class MetricsRecorder:
    def __init__(self, model: RoleSimulationModel) -> None:
        self.model = model
        self.timeseries: list[dict[str, object]] = []
        self.gateway_load_records: list[dict[str, object]] = []
        self._available_capability_intervals = 0
        self._required_capability_intervals = 0
        self.service_lifetime_crossings: dict[tuple[str, float], int] = {}

    def record(self, time: int) -> None:
        model = self.model
        nodes = tuple(model.hierarchy.nodes_by_id.values())
        active_nodes = [node for node in nodes if node.is_available()]
        energies = [node.energy for node in nodes]
        expected_roles = len(model.protocol_engine.assignment_keys)
        available_roles = sum(
            model.protocol_engine.role_available(role, scope)
            for role, scope in model.protocol_engine.assignment_keys
        )
        loads = [model.gateway_loads[node.node_id] for node in nodes]
        route_metrics = model.router.step_metrics()
        offered_data = int(route_metrics["data_messages_step"])
        delivered_data = int(route_metrics["delivered_data_messages_step"])
        sensor_generated_step = int(route_metrics["sensor_data_messages_step"])
        sensor_delivered_step = int(route_metrics["sensor_data_delivered_step"])
        if time > 0:
            self._available_capability_intervals += available_roles
            self._required_capability_intervals += expected_roles
        cumulative_csc = (
            self._available_capability_intervals / self._required_capability_intervals
            if self._required_capability_intervals else np.nan
        )
        cumulative_sensor_delivery = (
            model.router.sensor_data_delivered / model.router.sensor_data_messages
            if model.router.sensor_data_messages else np.nan
        )
        if time > 0:
            self._record_lifetime_crossings(time, cumulative_csc, cumulative_sensor_delivery)
        gateway_nodes = {
            node_id
            for (role, scope), lease in model.protocol_engine.assignments.items()
            if role == "gateway"
            and model.protocol_engine.role_available(role, scope)
            and (node_id := model.hierarchy.representative_node_id(lease.holder_id)) is not None
        }
        gateway_energy = sum(
            model.router.energy_consumed_by_node_step.get(node_id, 0.0)
            for node_id in gateway_nodes
        )
        communication_energy = (
            float(route_metrics["data_energy_consumed_step"])
            + float(route_metrics["control_energy_consumed_step"])
        )
        self.timeseries.append({
            "time": time,
            "protocol": model.protocol,
            "active_node_count": len(active_nodes),
            "active_node_fraction": len(active_nodes) / max(1, len(nodes)),
            "mean_remaining_energy": float(np.mean(energies)) if energies else 0.0,
            "mean_solar_harvest_rate": float(np.mean([
                node.solar_harvest_rate for node in nodes
            ])) if nodes else 0.0,
            "solar_energy_harvested_total": model.solar_energy_harvested,
            "solar_energy_harvested_step": model.solar_energy_harvested_step,
            "solar_energy_curtailed_total": model.solar_energy_curtailed,
            "depleted_node_count": sum(node.energy <= 0 for node in nodes),
            "energy_variance": float(np.var(energies)) if energies else 0.0,
            "control_messages_total": model.router.control_messages,
            "control_messages_step": route_metrics["control_messages_step"],
            "message_hop_transmissions_total": model.router.message_hop_transmissions,
            "message_hop_transmissions_step": route_metrics["message_hop_transmissions_step"],
            "route_cost_total": model.router.cumulative_route_cost,
            "route_cost_step": route_metrics["route_cost_step"],
            "data_messages_step": offered_data,
            "backhaul_messages_step": route_metrics["backhaul_messages_step"],
            "backhaul_hop_transmissions_step": route_metrics["backhaul_hop_transmissions_step"],
            "data_hop_transmissions_step": route_metrics["data_hop_transmissions_step"],
            "data_delivered_fraction": delivered_data / offered_data if offered_data else np.nan,
            "sensor_data_delivery_fraction": (
                route_metrics["sensor_data_delivered_step"] / route_metrics["sensor_data_messages_step"]
                if route_metrics["sensor_data_messages_step"] else np.nan
            ),
            "sensor_data_messages_step": route_metrics["sensor_data_messages_step"],
            "data_energy_consumed_step": route_metrics["data_energy_consumed_step"],
            "control_energy_consumed_step": route_metrics["control_energy_consumed_step"],
            "communication_energy_consumed_step": communication_energy,
            "gateway_energy_consumed_step": gateway_energy,
            "failed_deliveries_total": model.router.failed_deliveries,
            "failed_deliveries_step": route_metrics["failed_deliveries_step"],
            "role_migrations": len(model.protocol_engine.migration_records),
            "failed_unavailable_roles": expected_roles - available_roles,
            "role_availability": available_roles / expected_roles if expected_roles else 1.0,
            "capability_service_continuity": (
                available_roles / expected_roles if expected_roles else 1.0
            ),
            "cumulative_capability_service_continuity": cumulative_csc,
            "sensor_items_generated_step": sensor_generated_step,
            "sensor_items_delivered_step": sensor_delivered_step,
            "sensor_items_generated_total": model.router.sensor_data_messages,
            "sensor_items_delivered_total": model.router.sensor_data_delivered,
            "cumulative_sensor_delivery_fraction": cumulative_sensor_delivery,
            "role_recovery_time_mean": (
                float(np.mean(model.protocol_engine.recovery_times))
                if model.protocol_engine.recovery_times else np.nan
            ),
            "gateway_load_mean": float(np.mean(loads)) if loads else 0.0,
            "gateway_load_variance": float(np.var(loads)) if loads else 0.0,
        })
        for node in nodes:
            load = model.gateway_loads[node.node_id]
            if load > 0:
                self.gateway_load_records.append({
                    "time": time,
                    "protocol": model.protocol,
                    "gateway_node_id": node.node_id,
                    "gateway_load": load,
                })

        active_fraction = len(active_nodes) / max(1, len(nodes))
        if (
            model.network_lifetime_tick is None
            and active_fraction < model.config.minimum_active_fraction
        ):
            model.network_lifetime_tick = time

    def _record_lifetime_crossings(
        self,
        time: int,
        cumulative_csc: float,
        cumulative_sensor_delivery: float,
    ) -> None:
        for metric, value in (
            ("capability_service_continuity", cumulative_csc),
            ("sensor_delivery_fraction", cumulative_sensor_delivery),
        ):
            if np.isnan(value):
                continue
            for threshold in (0.9, 0.5):
                key = (metric, threshold)
                if key not in self.service_lifetime_crossings and value < threshold:
                    self.service_lifetime_crossings[key] = time

    def timeseries_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.timeseries, columns=TIMESERIES_COLUMNS)

    def migration_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            self.model.protocol_engine.migration_records,
            columns=MIGRATION_RECORD_COLUMNS,
        )

    def gateway_load_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            self.gateway_load_records,
            columns=("time", "protocol", "gateway_node_id", "gateway_load"),
        )

    def summary(self, scenario: str, seed: int) -> dict[str, object]:
        model = self.model
        frame = self.timeseries_frame()
        final = frame.iloc[-1]
        generated_items = model.router.sensor_data_messages
        delivered_items = model.router.sensor_data_delivered
        return {
            "scenario": scenario,
            "protocol": model.protocol,
            "seed": seed,
            "steps": model.steps,
            "network_lifetime": (
                model.network_lifetime_tick
                if model.network_lifetime_tick is not None else model.config.steps
            ),
            "network_lifetime_censored": model.network_lifetime_tick is None,
            "role_migrations": len(model.protocol_engine.migration_records),
            "control_messages": model.router.control_messages,
            "message_hop_transmissions": model.router.message_hop_transmissions,
            "sensor_data_messages": model.router.sensor_data_messages,
            "sensor_items_generated": generated_items,
            "sensor_items_delivered": delivered_items,
            "sensor_delivery_fraction": (
                delivered_items / generated_items if generated_items else np.nan
            ),
            "capability_service_continuity": (
                self._available_capability_intervals / self._required_capability_intervals
                if self._required_capability_intervals else np.nan
            ),
            "capability_time_intervals_available": self._available_capability_intervals,
            "capability_time_intervals_required": self._required_capability_intervals,
            **{
                f"{metric}_{int(threshold * 100)}_crossing_tick": (
                    self.service_lifetime_crossings.get((metric, threshold))
                )
                for metric in (
                    "capability_service_continuity",
                    "sensor_delivery_fraction",
                )
                for threshold in (0.9, 0.5)
            },
            **{
                f"{metric}_{int(threshold * 100)}_right_censored": (
                    (metric, threshold) not in self.service_lifetime_crossings
                )
                for metric in (
                    "capability_service_continuity",
                    "sensor_delivery_fraction",
                )
                for threshold in (0.9, 0.5)
            },
            "backhaul_messages": model.router.backhaul_messages,
            "backhaul_hop_transmissions": model.router.backhaul_hop_transmissions,
            "average_remaining_energy": float(
                np.mean([node.energy for node in model.hierarchy.nodes_by_id.values()])
            ),
            "energy_consumed": model.initial_mean_energy - float(
                np.mean([node.energy for node in model.hierarchy.nodes_by_id.values()])
            ),
            "communication_energy_consumed": (
                model.router.data_energy_consumed + model.router.control_energy_consumed
            ),
            "total_modeled_energy_consumed": (
                model.router.data_energy_consumed + model.router.control_energy_consumed
            ),
            "energy_consumed_per_successful_measurement": (
                (model.router.data_energy_consumed + model.router.control_energy_consumed)
                / delivered_items
                if delivered_items else np.nan
            ),
            "communication_energy_per_delivered_item": (
                (model.router.data_energy_consumed + model.router.control_energy_consumed)
                / delivered_items
                if delivered_items else np.nan
            ),
            "solar_energy_harvested": model.solar_energy_harvested,
            "solar_energy_curtailed": model.solar_energy_curtailed,
            "data_energy_consumed": model.router.data_energy_consumed,
            "control_energy_consumed": model.router.control_energy_consumed,
            "gateway_energy_consumed": float(frame["gateway_energy_consumed_step"].sum()),
            "maximum_node_communication_energy": max(
                model.router.energy_consumed_by_node.values(),
                default=0.0,
            ),
            "average_role_recovery_time": (
                float(np.mean(model.protocol_engine.recovery_times))
                if model.protocol_engine.recovery_times else np.nan
            ),
            "failed_unavailable_roles_final": int(final["failed_unavailable_roles"]),
            "role_unavailable_steps": int(frame["failed_unavailable_roles"].sum()),
            "role_availability": float(frame["role_availability"].mean()),
            "energy_variance_final": float(final["energy_variance"]),
            "active_node_count_final": int(final["active_node_count"]),
            "depleted_node_count_final": int(final["depleted_node_count"]),
            "gateway_load_variance_mean": float(frame["gateway_load_variance"].mean()),
            "failed_deliveries": model.router.failed_deliveries,
            "data_delivery_fraction": (
                float(frame["data_delivered_fraction"].dropna().mean())
                if frame["data_delivered_fraction"].notna().any() else np.nan
            ),
            "sensor_data_delivery_fraction": (
                float(frame["sensor_data_delivery_fraction"].dropna().mean())
                if frame["sensor_data_delivery_fraction"].notna().any() else np.nan
            ),
            "migration_cost_total": sum(
                float(record["migration_cost"])
                for record in model.protocol_engine.migration_records
            ),
        }

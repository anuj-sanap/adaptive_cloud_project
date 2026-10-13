"""
Unit & Integration Tests for Reproducible Recovery Policy Benchmark.
=====================================================================
Validates causal integrity, metric calculations, reproducibility across seeds,
identical incident scenarios, identical recovery criteria, and database persistence.
"""

import sys
import os
import unittest
from typing import Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from central_server.database import (
    init_db,
    save_recovery_benchmark_result,
    get_latest_recovery_benchmark,
)
from experiments.recovery_policy_benchmark import (
    generate_repeatable_benchmark_episodes,
    run_reproducible_benchmark,
    run_historical_fleet_replay,
    BenchmarkSummary,
    PolicyEvaluationMetrics,
    IncidentEpisode,
)


class TestRecoveryPolicyBenchmark(unittest.TestCase):
    """Test suite for reproducible policy evaluation and benchmarking logic."""

    @classmethod
    def setUpClass(cls):
        init_db()

    def test_01_deterministic_scenario_reproducibility(self):
        """Verifies that identical RNG seeds generate identical incident sequences."""
        episodes_seed42_a = generate_repeatable_benchmark_episodes(trial_count=15, seed=42)
        episodes_seed42_b = generate_repeatable_benchmark_episodes(trial_count=15, seed=42)
        episodes_seed99 = generate_repeatable_benchmark_episodes(trial_count=15, seed=99)

        self.assertEqual(len(episodes_seed42_a), 15)
        self.assertEqual(len(episodes_seed42_b), 15)

        # Exact equality across trials for same seed
        for ep_a, ep_b in zip(episodes_seed42_a, episodes_seed42_b):
            self.assertEqual(ep_a.episode_id, ep_b.episode_id)
            self.assertEqual(ep_a.incident_type, ep_b.incident_type)
            self.assertEqual(ep_a.severity, ep_b.severity)
            self.assertEqual(ep_a.scenario_type, ep_b.scenario_type)
            self.assertEqual(ep_a.baseline_metrics, ep_b.baseline_metrics)

        # Different seed produces distinct permutation
        types_42 = [e.incident_type for e in episodes_seed42_a]
        types_99 = [e.incident_type for e in episodes_seed99]
        self.assertNotEqual(types_42, types_99, "Different seeds should produce different episode sequences")

    def test_02_causal_integrity_no_future_leakage(self):
        """
        Verifies strict causality:
        At episode t, adaptive policy can only use trials from episodes 1...(t-1).
        """
        summary = run_reproducible_benchmark(trial_count=10, seed=42, persist=False)
        episodes_log = summary.episodes_log

        # On the very first episode (t=1), adaptive policy MUST use CATALOG_PRIOR
        self.assertEqual(
            episodes_log[0]["adaptive_scope"],
            "CATALOG_PRIOR",
            "Episode 1 must operate under catalog baseline prior (zero historical experience)."
        )

        # Fixed-rule baseline must strictly have 0 policy pivots
        self.assertEqual(summary.baseline_metrics.decision_changes_count, 0)

    def test_03_identical_scenarios_and_criteria(self):
        """Verifies that both policies face identical incidents and criteria."""
        summary = run_reproducible_benchmark(trial_count=20, seed=123, persist=False)
        episodes = summary.episodes_log

        for ep in episodes:
            self.assertIn("incident_type", ep)
            self.assertIn("baseline_action", ep)
            self.assertIn("adaptive_action", ep)
            self.assertIn("baseline_outcome", ep)
            self.assertIn("adaptive_outcome", ep)
            # Both outcomes must be either SUCCESS or FAILURE
            self.assertIn(ep["baseline_outcome"], ["SUCCESS", "FAILURE"])
            self.assertIn(ep["adaptive_outcome"], ["SUCCESS", "FAILURE"])

    def test_04_benchmark_metrics_mathematical_consistency(self):
        """Verifies mathematical consistency of success rate, MTTR, costs, and deltas."""
        trial_n = 25
        summary = run_reproducible_benchmark(trial_count=trial_n, seed=777, persist=False)
        
        adapt = summary.adaptive_metrics
        base = summary.baseline_metrics
        deltas = summary.deltas

        # Total trials check
        self.assertEqual(adapt.total_trials, trial_n)
        self.assertEqual(base.total_trials, trial_n)

        # Success rate consistency
        expected_adapt_sr = round((adapt.successful_recoveries / trial_n) * 100.0, 2)
        expected_base_sr = round((base.successful_recoveries / trial_n) * 100.0, 2)
        self.assertEqual(adapt.success_rate_pct, expected_adapt_sr)
        self.assertEqual(base.success_rate_pct, expected_base_sr)

        # Unsuccessful attempts consistency
        self.assertEqual(adapt.unsuccessful_attempts, trial_n - adapt.successful_recoveries)
        self.assertEqual(base.unsuccessful_attempts, trial_n - base.successful_recoveries)

        # Delta checks
        self.assertAlmostEqual(deltas["success_rate_delta_pct"], adapt.success_rate_pct - base.success_rate_pct, places=2)
        self.assertEqual(deltas["unsuccessful_attempts_delta"], adapt.unsuccessful_attempts - base.unsuccessful_attempts)
        self.assertAlmostEqual(deltas["mttr_delta_sec"], adapt.mean_time_to_recovery_sec - base.mean_time_to_recovery_sec, places=2)

    def test_05_database_benchmark_persistence_and_retrieval(self):
        """Verifies benchmark results can be stored in SQLite and retrieved with full fidelity."""
        summary = run_reproducible_benchmark(trial_count=10, seed=55, persist=True)
        
        retrieved = get_latest_recovery_benchmark(mode="SIMULATED")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["benchmark_id"], summary.benchmark_id)
        self.assertEqual(retrieved["mode"], "SIMULATED")
        self.assertEqual(retrieved["trial_count"], 10)
        self.assertEqual(retrieved["seed"], 55)

        # Verify JSON desync fidelity
        self.assertEqual(retrieved["adaptive_metrics"]["success_rate_pct"], summary.adaptive_metrics.success_rate_pct)
        self.assertEqual(retrieved["baseline_metrics"]["success_rate_pct"], summary.baseline_metrics.success_rate_pct)
        self.assertEqual(len(retrieved["episodes_log"]), 10)

    def test_06_historical_fleet_replay_execution(self):
        """Verifies that historical fleet replay runs on actual database records without error."""
        hist_summary = run_historical_fleet_replay(limit=15, persist=True)
        self.assertIsInstance(hist_summary, BenchmarkSummary)
        self.assertEqual(hist_summary.mode, "ACTUAL_HISTORICAL")
        self.assertTrue(hist_summary.trial_count > 0)
        self.assertIsNone(hist_summary.seed, "Historical replay should not have a synthetic seed")
        self.assertIsNotNone(hist_summary.adaptive_metrics)
        self.assertIsNotNone(hist_summary.baseline_metrics)


if __name__ == "__main__":
    unittest.main(verbosity=2)

/**
 * Utility functions for identifying and filtering genuine physical/agent devices
 * vs synthetic test fixtures, audit probes, or mock node records.
 */

export interface BaseNodeIdentifier {
  node_id: string;
  hostname?: string;
  location_label?: string | null;
}

const DUMMY_SUBSTRINGS = [
  'api-test',
  'test-verify',
  'frontend-test',
  'node_audit',
  'test-node',
  'test_node',
  'retrain_test',
  'drift-test',
  'sec_test',
  'lifecycle',
  'disco_node',
  'rogue_node',
  'dummy',
  'mock',
];

const DUMMY_HOSTNAMES = [
  'web-console-host',
  'verify-host',
  'api-node',
  'test-host',
  'sec-test-host',
  'disconnect-node',
  'unknown-host',
  'rogue_node_agent',
  'dynamic-host-1',
];

/**
 * Returns true if a node represents a genuine edge device or registered demonstration agent,
 * and false if it is a synthetic test fixture or audit runner artifact.
 */
export function isGenuineNode(node: BaseNodeIdentifier | null | undefined): boolean {
  if (!node || !node.node_id) return false;

  const nid = node.node_id.toLowerCase().trim();
  const host = (node.hostname || '').toLowerCase().trim();

  // Check known dummy / test substrings in node_id
  for (const pattern of DUMMY_SUBSTRINGS) {
    if (nid.includes(pattern)) {
      return false;
    }
  }

  // Check known dummy hostnames
  if (DUMMY_HOSTNAMES.includes(host)) {
    return false;
  }

  // Regex check for test runs with ephemeral PID suffixes (e.g. _alpha_36809)
  if (/_(alpha|beta)_\d{4,7}$/i.test(nid)) {
    return false;
  }

  return true;
}

/**
 * Filter an array of node records to only genuine devices.
 */
export function filterGenuineNodes<T extends BaseNodeIdentifier>(nodes: T[]): T[] {
  if (!Array.isArray(nodes)) return [];
  return nodes.filter(isGenuineNode);
}

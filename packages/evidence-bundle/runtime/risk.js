import { EvidenceBundleError } from "./types.js";

const FACTORS = new Set([
  "goal_divergence_indicator",
  "harm_realization_capability",
  "oversight_resistance_indicator",
]);
const STATUSES = new Set(["PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"]);
const STRENGTHS = new Set(["DIRECT", "CORROBORATED", "INDIRECT", "NONE"]);

export function validateRiskDiagnosis(value) {
  requireObject(value, "Risk Diagnosis");
  exactKeys(value, [
    "schema_version", "evaluator_version", "created_at", "policy_id",
    "policy_sha256", "findings", "pathways", "interventions", "diagnostics",
    "provenance",
  ], "Risk Diagnosis");
  if (
    value.schema_version !== "aet-risk-diagnosis/1.0" ||
    typeof value.evaluator_version !== "string" || value.evaluator_version.length === 0 ||
    !isTimestamp(value.created_at) ||
    typeof value.policy_id !== "string" ||
    !isDigest(value.policy_sha256) ||
    !Array.isArray(value.findings) ||
    !Array.isArray(value.pathways) ||
    !Array.isArray(value.interventions) ||
    !Array.isArray(value.diagnostics) ||
    !isObject(value.provenance)
  ) {
    throw new EvidenceBundleError("invalid_risk_diagnosis", "Risk Diagnosis v1 is invalid");
  }
  for (const forbidden of ["overall_score", "trust_score", "model_motive", "autonomous_action"]) {
    if (Object.hasOwn(value, forbidden)) {
      throw new EvidenceBundleError("invalid_risk_authority", `Risk Diagnosis forbids ${forbidden}`);
    }
  }
  for (const finding of value.findings) {
    validateFinding(finding);
  }
  for (const pathway of value.pathways) {
    requireObject(pathway, "Risk pathway");
    if (
      typeof pathway.pathway_id !== "string" || pathway.pathway_id.length === 0 ||
      typeof pathway.context_key !== "string" || pathway.context_key.length === 0 ||
      !Array.isArray(pathway.factors) || !pathway.factors.every((item) => {
        validateFinding(item);
        return true;
      }) ||
      !sourceRefs(pathway.ordered_refs) ||
      !STATUSES.has(pathway.status) ||
      !stringArray(pathway.causal_limitations)
    ) {
      throw new EvidenceBundleError("invalid_risk_pathway", "Risk pathway is invalid");
    }
  }
  if (value.interventions.some((item) =>
    !isObject(item) || item.authority !== "PROPOSED" ||
    typeof item.intervention_id !== "string" || item.intervention_id.length === 0 ||
    typeof item.context_key !== "string" || item.context_key.length === 0 ||
    !Array.isArray(item.factor_combination) || !item.factor_combination.every((factor) => FACTORS.has(factor)) ||
    !stringArray(item.actions) || item.actions.length === 0 ||
    !sourceRefs(item.rationale_refs)
  )) {
    throw new EvidenceBundleError("invalid_risk_authority", "Risk interventions must remain PROPOSED");
  }
  return {
    schema_version: "risk-diagnosis-validation/1.0",
    status: "PASS",
    factor_count: value.findings.length,
    pathway_count: value.pathways.length,
    intervention_count: value.interventions.length,
  };
}

export function validateRiskForecast(value) {
  requireObject(value, "Risk Forecast");
  exactKeys(value, [
    "schema_version", "created_at", "diagnosis_sha256", "calibration_sha256",
    "dataset_sha256", "forecasts", "gate_status", "limitations", "provenance",
  ], "Risk Forecast");
  if (
    value.schema_version !== "aet-risk-forecast/1.0" ||
    !isTimestamp(value.created_at) ||
    !isDigest(value.diagnosis_sha256) ||
    !isDigest(value.calibration_sha256) ||
    !isDigest(value.dataset_sha256) ||
    !["PASS", "FAIL"].includes(value.gate_status) ||
    !Array.isArray(value.forecasts) ||
    !stringArray(value.limitations) ||
    !isObject(value.provenance)
  ) {
    throw new EvidenceBundleError("invalid_risk_forecast", "Risk Forecast v1 is invalid");
  }
  if (Object.hasOwn(value, "overall_score") || Object.hasOwn(value, "trust_score")) {
    throw new EvidenceBundleError("invalid_risk_authority", "Risk Forecast forbids a holistic score");
  }
  for (const forecast of value.forecasts) {
    requireObject(forecast, "Pathway forecast");
    if (
      typeof forecast.pathway_id !== "string" || forecast.pathway_id.length === 0 ||
      typeof forecast.signature !== "string" || forecast.signature.length === 0 ||
      !new Set(["ELEVATED", "NOT_ELEVATED", "UNKNOWN"]).has(forecast.status) ||
      !Number.isInteger(forecast.support) || forecast.support < 0 ||
      !interval(forecast.interval) || !interval(forecast.baseline) ||
      typeof forecast.reason !== "string" || forecast.reason.length === 0
    ) {
      throw new EvidenceBundleError("invalid_risk_forecast", "Pathway forecast status is invalid");
    }
  }
  return {
    schema_version: "risk-forecast-validation/1.0",
    status: "PASS",
    gate_status: value.gate_status,
    forecast_count: value.forecasts.length,
  };
}

function requireObject(value, label) {
  if (!isObject(value)) {
    throw new EvidenceBundleError("invalid_risk_document", `${label} must be an object`);
  }
}

function validateFinding(finding) {
  requireObject(finding, "Risk finding");
  if (
    !FACTORS.has(finding.factor) ||
    typeof finding.observable !== "string" || finding.observable.length === 0 ||
    !STATUSES.has(finding.status) ||
    !STRENGTHS.has(finding.strength) ||
    !sourceRefs(finding.evidence_refs) ||
    !sourceRefs(finding.counter_evidence_refs) ||
    !isObject(finding.coverage) ||
    typeof finding.coverage.complete !== "boolean" ||
    !stringArray(finding.coverage.checked_surfaces) ||
    !stringArray(finding.coverage.gaps) ||
    typeof finding.coverage.observability_gap !== "boolean" ||
    !stringArray(finding.limitations) ||
    !stringArray(finding.does_not_prove) || finding.does_not_prove.length === 0 ||
    typeof finding.context_key !== "string" || finding.context_key.length === 0 ||
    !stringArray(finding.asset_ids) ||
    !stringArray(finding.monitoring_surface_ids) ||
    !stringArray(finding.signal_codes) ||
    !stringArray(finding.order_keys)
  ) {
    throw new EvidenceBundleError("invalid_risk_finding", "Risk finding is invalid");
  }
  if (finding.status === "FAIL" && finding.evidence_refs.length === 0) {
    throw new EvidenceBundleError("invalid_risk_finding", "FAIL requires evidence references");
  }
  if (finding.status === "PASS" && finding.coverage.complete !== true) {
    throw new EvidenceBundleError("invalid_risk_finding", "PASS requires complete coverage");
  }
}

function exactKeys(value, keys, label) {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new EvidenceBundleError("invalid_risk_document", `${label} fields are invalid`);
  }
}

function isObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringArray(value) {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function sourceRefs(value) {
  return Array.isArray(value) && value.every((item) =>
    isObject(item) && typeof item.ref === "string" && item.ref.length > 0 &&
    ["record_id", "source_order_id", "source_type"].every((key) =>
      item[key] === null || typeof item[key] === "string"
    )
  );
}

function interval(value) {
  return isObject(value) && ["low", "high"].every((key) =>
    value[key] === null || typeof value[key] === "number"
  );
}

function isTimestamp(value) {
  return typeof value === "string" && value.endsWith("Z") && Number.isFinite(Date.parse(value));
}

function isDigest(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/u.test(value);
}

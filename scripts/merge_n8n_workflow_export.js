const fs = require("fs");

const [, , localPath, livePath, outputPath] = process.argv;

if (!localPath || !livePath || !outputPath) {
  console.error("Usage: node merge_n8n_workflow_export.js <local.json> <live.json> <output.json>");
  process.exit(2);
}

function readWorkflow(path) {
  const data = JSON.parse(fs.readFileSync(path, "utf8"));
  return Array.isArray(data) ? data[0] : data;
}

const localWorkflow = readWorkflow(localPath);
const liveWorkflow = readWorkflow(livePath);
const liveNodesById = new Map((liveWorkflow.nodes || []).map((node) => [node.id, node]));
const liveNodesByName = new Map((liveWorkflow.nodes || []).map((node) => [node.name, node]));

for (const node of localWorkflow.nodes || []) {
  const liveNode = liveNodesById.get(node.id) || liveNodesByName.get(node.name);
  if (!liveNode) {
    continue;
  }

  if (liveNode.credentials) {
    node.credentials = liveNode.credentials;
  }

  if (node.parameters && liveNode.parameters && node.parameters.url && liveNode.parameters.url) {
    node.parameters.url = liveNode.parameters.url;
  }
}

const mergedWorkflow = {
  ...liveWorkflow,
  ...localWorkflow,
  id: liveWorkflow.id || localWorkflow.id,
  name: liveWorkflow.name || localWorkflow.name,
  active: liveWorkflow.active === true,
  createdAt: liveWorkflow.createdAt,
  updatedAt: liveWorkflow.updatedAt,
  versionId: liveWorkflow.versionId || localWorkflow.versionId,
};

fs.writeFileSync(outputPath, JSON.stringify(mergedWorkflow, null, 2));

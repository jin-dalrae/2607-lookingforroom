import { handleQueueApi } from "../lib/queue-api.js";

export async function onRequest(context) {
  const { request, env, params } = context;
  const segments = Array.isArray(params.path) ? params.path : [];
  return handleQueueApi(request, env, segments, request.method);
}
export function GET() {
  return Response.json({
    status: 'ok',
    projectId: process.env.SPECCHECK_PROJECT_ID ?? null,
    backendUrl: process.env.NEXT_PUBLIC_SPECCHECK_AGENT_URL ?? 'http://127.0.0.1:8000',
  });
}

# Optional local tracing demonstration

Use an existing saved Session 1 run. This adds no service, credentials, dependencies or model calls:

```sh
python -m workshop.trace_view state/reading-conflict/trace.jsonl
```

Open `trace-view.html` beside the source trace in a browser. Follow validation → model proposal → PDF page review → proposed correction → accepted findings → revalidation → finalization. Your unfinished Session 1 TODOs show a shorter path. After completing them, generate another offline run to inspect the recovery steps. Show its `review.html` alongside the trace to inspect the evidence citations and the original/current invoice.

Explain that proposals are distinct from accepted corrections, and only subsequent deterministic validation establishes the recommendation. This remains a recommendation for separate human review.

The view projects recognised event types and limited structured metadata. It omits prompts, free-text notes, excerpts, identifiers and private reasoning. Unknown events are counted but hidden. A model-result event followed by an investigation event can refer to the same call. The trace has no span timing or actual provider cost data, so the view does not infer either. Client spending reservations are not actual usage charges.

The generated page is self-contained and uses no scripts or external network assets. Keep source traces and human review reports local unless you separately review their contents for sharing; they contain more data than the projected trace view.

On the Session 3 branches, the same viewer also recognises Session 2 tool requests/results, page reads, answers and terminal stops. [Session 3](session3.md) generates matched scripted diagnosis examples and regenerated projected views for export; private argument/evidence text remains omitted.

For Session 3 local diagnosis, use `python -m workshop.session3 context --input
outputs/session3-demo --output outputs/session3-private-context` and open its
`index.html`. This separate private view shows the recorded invoice, configured
prompt, tool arguments/results, validation questions and final answer. It does
not capture exact API payloads or private reasoning. Keep the detailed directory
local; the sharing exporter continues to regenerate only restricted views.

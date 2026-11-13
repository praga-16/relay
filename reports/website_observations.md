# Vaani website observations

Inspected https://www.vaani.dev/ on 2026-11-12 through a text-rendered web fetch, not a signed-in product session. No voice call was placed and no audio was listened to. These are assistant observations pending the candidate's personal review.

* Stood out: the landing page groups voice-agent capabilities around turn taking, language/dialect switching and latency; it links documentation and presents customer-story sections.
* Confusing: the fetched page showed 0M+, 0.0% and <0ms in headline metrics, while elsewhere describing approximately 450ms p90 latency. This may be an animation/text-fetch artifact, not the normal visual experience. The text representation alone cannot settle that.
* Improvement: provide meaningful static metric fallbacks and clarify the measurement boundary and workload behind the latency claim. Distinguish speech response latency from the full application's user-perceived latency.

No signup, customer experience, or product performance is claimed. This website is project/report context only and is never answer evidence in RAG.

Engineering documentation consulted separately: https://console.groq.com/docs/models ; https://console.groq.com/docs/rate-limits ; https://console.groq.com/docs/reasoning ; https://console.groq.com/docs/api-reference ; https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 .

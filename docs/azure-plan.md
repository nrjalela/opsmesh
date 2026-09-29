# OpsMesh Live on Azure: parked plan

Status: **paused** (2026-09-30) in favour of the GitHub Actions live mode. Kept here so it can be picked up later.

## Findings (checked against Microsoft Learn, September 2026)

- **No Claude model is deployable in an Australian Azure region.** For `claude-sonnet-5-5` the choices are:
  - *Hosted on Azure, Data Zone Standard (US)* (recommended): processed entirely on Azure infrastructure inside the US.
  - *Hosted on Anthropic, Global Standard* (US regions or Sweden Central): processed on Anthropic infrastructure, possibly outside Azure and the chosen region.
  - So the Foundry resource would sit in East US 2 and everything else in Australia East. Never claim Australian data residency for inference.
- **Subscription must be pay-as-you-go with a card.** Free trial, student and credit-only subscriptions get zero Claude quota. Pay-as-you-go defaults to 40 RPM / 40k ITPM / 8k OTPM for Sonnet 5.5. Billing goes through Azure Marketplace at Claude API prices.
- **Keyless auth works:** `AnthropicFoundry(azure_ad_token_provider=...)` with scope `https://ai.azure.com/.default`, and the managed identity needs the *Cognitive Services User* role.
- **The server-side refusal fallback isn't used on Foundry**; refusals route to a person.
- **LangGraph checkpointer:** `langchain-azure-cosmosdb` (Microsoft-maintained) includes a Cosmos DB checkpoint saver.
- **To verify:** Flex Consumption with Python 3.13 in Australia East, and whether Marketplace charges appear in Azure budgets.

## Architecture sketch

Mailbox (Outlook.com with a Logic Apps trigger, or Microsoft 365 via Graph) → Blob Storage → Event Grid → Azure Functions (Flex Consumption):

- **Gate:** allowlist, PDF limits, daily cap.
- **Pipeline:** the existing LangGraph pipeline, with Claude via Foundry and the unchanged engine.
- **Storage:** Cosmos DB serverless for checkpoints, runs, the live ledger, approval tokens and the audit log.
- **Approvals:** by email via Azure Communication Services, with signed, single-use, expiring links. Opening a link shows a confirmation page; only a POST acts, because email scanners pre-open links.
- **Other pieces:** Key Vault for the HMAC key, Application Insights with one failure alert, Bicep + `azd up` / `azd down`.

**Why Functions over Container Apps:** the dependencies are pip wheels, so no container registry is needed (about US$5/month saved).

**Why Cosmos serverless over Table Storage:** it has a real LangGraph checkpointer and no 64 KB property limit, and costs only cents at this volume.

## Estimated cost

About US$1–3 a month, with Claude capped at 5 invoices/day. That's within an A$8 budget.

## Phase 0 steps for the account owner

1. Pay-as-you-go subscription with a card.
2. MFA on the account.
3. A$8 budget with email alerts.
4. Run `az login` and `azd auth login`.
5. Accept the Azure Marketplace terms for Claude once.

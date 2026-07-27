---
tags: [nautilus, execution, order-types]
---
# Nautilus Order Types & Contingency Matrix

## Time-In-Force (TIF)
* **IOC (Immediate Or Cancel)**: Fills instantly or cancels remaining.
* **FOK (Fill Or Kill)**: Entire order must fill immediately or be killed.
* **GTC (Good 'Til Cancelled)**: Active until explicitly cancelled.
* **DAY**: Active only for current market session.

## Contingency Chains
* **OCO (One-Cancels-Other)**: Dual exit bracket (Take Profit Limit + Stop Loss Stop).
* **OTO (One-Triggers-Other)**: Entry order fill automatically places the exit bracket.
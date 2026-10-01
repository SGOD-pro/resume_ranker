"""
Handlers package — Modular AWS Lambda entry points
=================================================
Each handler imports only its specific tier dependencies, minimizing
cold starts, memory footprints, and cross-tier coupling.
"""

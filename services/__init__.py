"""
services package

Business-logic layer that sits ABOVE the raw database models. Anything
here operates on data already loaded by database/ (Modules 1-3), and
implements a specific piece of business functionality - data cleaning,
validation, KPI calculation, forecasting, etc. - one file per concern.

Modules in dashboard/ and ai/ should call into services/, not query
the database directly, so business rules live in exactly one place.
"""

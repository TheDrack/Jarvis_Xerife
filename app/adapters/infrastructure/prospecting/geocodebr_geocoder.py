"""Local Brazilian address geocoding adapter backed by Ipea's geocodebr/CNEFE.

The optional dependency is imported lazily so the core Jarvis installation does
not download the CNEFE dataset or install geospatial packages at startup.
"""
from __future__ import annotations

from typing import Sequence

from app.domain.prospecting.contracts import ProspectCompany
from app.domain.prospecting.geography import (
    AddressGeocoding,
    GeoCoordinate,
    GeocodingPrecision,
    GeocodingStatus,
)


_PRECISION_MAP = {
    "numero": GeocodingPrecision.PREMISE,
    "numero_aproximado": GeocodingPrecision.INTERPOLATED,
    "logradouro": GeocodingPrecision.STREET,
    "cep": GeocodingPrecision.POSTAL_CODE,
    "localidade": GeocodingPrecision.LOCALITY,
    "municipio": GeocodingPrecision.REGION,
}


class GeocodeBrGeocoder:
    """Batch geocoder using the Brazilian CNEFE address dataset."""

    provider_name = "geocodebr:cnefe"

    def geocode_companies(
        self, companies: Sequence[ProspectCompany]
    ) -> list[AddressGeocoding]:
        if not companies:
            return []

        for company in companies:
            if company.country != "BR":
                raise ValueError("GeocodeBrGeocoder only supports Brazilian companies")
            if not company.geocoding_address:
                raise ValueError("company must have a postal address before geocoding")

        try:
            import polars as pl
            from geocodebr import definir_campos, geocode
        except ImportError as exc:
            raise RuntimeError(
                "The optional geocodebr provider is not installed. "
                "Install it with: python -m pip install 'jarvis-assistant[geocodebr]'"
            ) from exc

        rows = []
        for row_id, company in enumerate(companies):
            street = company.street_name
            if street and company.street_type:
                street = f"{company.street_type} {street}"
            rows.append(
                {
                    "_jarvis_row_id": row_id,
                    "logradouro": street,
                    "numero": company.street_number,
                    "cep": company.postal_code,
                    "localidade": company.neighborhood,
                    "municipio": company.city,
                    "estado": company.state,
                }
            )

        fields = definir_campos(
            logradouro="logradouro",
            numero="numero",
            cep="cep",
            localidade="localidade",
            municipio="municipio",
            estado="estado",
        )
        table = geocode(
            enderecos=pl.DataFrame(rows),
            campos_endereco=fields,
            resultado_completo=False,
            resolver_empates=True,
            verboso=False,
        )
        output_rows = table.to_pylist()
        by_id = {
            row["_jarvis_row_id"]: row
            for row in output_rows
            if "_jarvis_row_id" in row
        }
        if len(by_id) != len(companies):
            raise RuntimeError(
                "geocodebr output did not preserve the input row identifiers; "
                "refusing to associate coordinates with the wrong company"
            )

        results = []
        for row_id, company in enumerate(companies):
            row = by_id[row_id]
            latitude = row.get("lat")
            longitude = row.get("lon")
            precision_name = str(row.get("precisao") or "").strip().casefold()
            precision = _PRECISION_MAP.get(precision_name)
            if latitude is None or longitude is None:
                results.append(
                    AddressGeocoding(
                        address=company.geocoding_address,
                        status=GeocodingStatus.FAILED,
                        provider=self.provider_name,
                    )
                )
                continue

            if precision is None:
                precision = GeocodingPrecision.UNKNOWN
            status = (
                GeocodingStatus.SUCCESS
                if precision is GeocodingPrecision.PREMISE
                else GeocodingStatus.PARTIAL
            )
            results.append(
                AddressGeocoding(
                    address=company.geocoding_address,
                    formatted_address=row.get("endereco_encontrado") or None,
                    status=status,
                    coordinate=GeoCoordinate(
                        latitude=float(latitude),
                        longitude=float(longitude),
                        accuracy_m=(
                            float(row["desvio_metros"])
                            if row.get("desvio_metros") is not None
                            else None
                        ),
                    ),
                    precision=precision,
                    provider=self.provider_name,
                    confidence=None,
                )
            )
        return results


__all__ = ["GeocodeBrGeocoder"]

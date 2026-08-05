from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re


EXPECTED_HEADER = "fecha|tipo|descripcion|cuenta|sector|importe"
ALLOWED_TYPES = {"Ingreso", "Gasto", "Traspaso"}
TRANSFER_SECTOR = "Traspaso entre cuentas"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class BulkImportError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedTransfer:
    line_number: int
    fecha: str
    cuenta: str
    sector: str
    importe: Decimal


def decode_txt_content(content):
    if isinstance(content, str):
        return content
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BulkImportError("El archivo debe estar codificado en UTF-8.") from exc


def parse_date(value, line_number):
    if not DATE_PATTERN.fullmatch(value):
        raise BulkImportError(f"Linea {line_number}: la fecha debe tener formato yyyy-mm-dd.")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise BulkImportError(f"Linea {line_number}: la fecha no es valida.") from exc
    return value


def parse_amount(value, line_number):
    if not value:
        raise BulkImportError(f"Linea {line_number}: el importe es obligatorio.")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise BulkImportError(f"Linea {line_number}: el importe no es un numero valido.") from exc
    if not amount.is_finite():
        raise BulkImportError(f"Linea {line_number}: el importe no es un numero valido.")
    if amount == 0:
        raise BulkImportError(f"Linea {line_number}: el importe no puede ser 0.")
    return amount


def validate_amount_sign(tipo, amount, line_number):
    if tipo == "Ingreso" and amount <= 0:
        raise BulkImportError(f"Linea {line_number}: los ingresos deben tener importe positivo.")
    if tipo == "Gasto" and amount >= 0:
        raise BulkImportError(f"Linea {line_number}: los gastos deben tener importe negativo.")


def validate_transfer_pairs(transfers):
    unmatched = []
    for transfer in transfers:
        matching_index = next(
            (
                index
                for index, candidate in enumerate(unmatched)
                if candidate.fecha == transfer.fecha
                and candidate.sector == transfer.sector
                and abs(candidate.importe) == abs(transfer.importe)
                and candidate.importe * transfer.importe < 0
                and candidate.cuenta != transfer.cuenta
            ),
            None,
        )
        if matching_index is None:
            unmatched.append(transfer)
        else:
            unmatched.pop(matching_index)

    if unmatched:
        first = min(unmatched, key=lambda item: item.line_number)
        raise BulkImportError(
            f"Linea {first.line_number}: este traspaso no tiene una linea complementaria "
            "con la misma fecha, sector e importe absoluto, signo contrario y otra cuenta."
        )


def parse_bulk_transactions_txt(content, cuentas, sectores):
    text = decode_txt_content(content)
    lines = text.splitlines()
    if not lines:
        raise BulkImportError("El archivo esta vacio.")

    header = lines[0].strip("\ufeff")
    if header != EXPECTED_HEADER:
        raise BulkImportError(f"La cabecera debe ser exactamente: {EXPECTED_HEADER}")

    cuentas_validas = set(cuentas)
    sectores_validos = set(sectores)
    records = []
    transfers = []

    for line_number, raw_line in enumerate(lines[1:], start=2):
        if not raw_line.strip():
            continue

        columns = [column.strip() for column in raw_line.split("|")]
        if len(columns) != 6:
            raise BulkImportError(
                f"Linea {line_number}: se esperaban 6 columnas separadas por '|', "
                f"pero se encontraron {len(columns)}."
            )

        fecha, tipo, descripcion, cuenta, sector, importe_raw = columns
        fecha = parse_date(fecha, line_number)

        if tipo not in ALLOWED_TYPES:
            raise BulkImportError(
                f"Linea {line_number}: el tipo debe ser Ingreso, Gasto o Traspaso."
            )
        if tipo == "Traspaso" and sector != TRANSFER_SECTOR:
            raise BulkImportError(
                f"Linea {line_number}: los traspasos deben usar el sector '{TRANSFER_SECTOR}'."
            )
        if cuenta not in cuentas_validas:
            raise BulkImportError(f"Linea {line_number}: la cuenta '{cuenta}' no esta predefinida.")
        if sector not in sectores_validos:
            raise BulkImportError(f"Linea {line_number}: el sector '{sector}' no esta predefinido.")

        amount = parse_amount(importe_raw, line_number)
        validate_amount_sign(tipo, amount, line_number)

        records.append(
            {
                "fecha": fecha,
                "tipo": tipo,
                "descripcion": descripcion,
                "cuenta": cuenta,
                "sector": sector,
                "importe": float(amount),
            }
        )
        if tipo == "Traspaso":
            transfers.append(
                ParsedTransfer(
                    line_number=line_number,
                    fecha=fecha,
                    cuenta=cuenta,
                    sector=sector,
                    importe=amount,
                )
            )

    if not records:
        raise BulkImportError("El archivo no contiene registros.")

    validate_transfer_pairs(transfers)
    return records

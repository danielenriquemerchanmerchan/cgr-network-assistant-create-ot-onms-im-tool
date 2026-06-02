"""
test_resolver_sit_location.py
-----------------------------
Diagnostico rapido: verifica que catalogos.resolver_sit_location()
funcione contra inventario_hlx real, y de paso confirma los nombres
exactos (case-sensitive) de tabla y columnas.

Colocar en la raiz del proyecto (junto a app.py) y correr:
    python test_resolver_sit_location.py

Prueba con el CI que sabemos que Maximo rechaza:
    ANT_SRO_DOMA_H501_D016
"""

import psycopg2
from onms import catalogos


CI_PRUEBA = "ANT_SRO_DOMA_H501_D016"


def main():
    print("=" * 60)
    print("DIAGNOSTICO resolver_sit_location")
    print("=" * 60)

    # 1. Probar la funcion tal cual quedo
    print(f"\n[1] catalogos.resolver_sit_location('{CI_PRUEBA}')")
    res = catalogos.resolver_sit_location(CI_PRUEBA)
    print(f"    -> {res!r}")
    if res:
        print(f"    OK: el CI esta en inventario_hlx con SIT_LOCATION={res}")
    else:
        print(f"    None: el CI no se encontro (o columna/tabla mal nombrada)")

    # 2. Verificacion directa de nombres de columnas en la tabla
    print(f"\n[2] Columnas reales de inventario_hlx (information_schema):")
    try:
        conn = psycopg2.connect(
            host=catalogos.PG_HOST, port=catalogos.PG_PORT,
            user=catalogos.PG_USER, password=catalogos.PG_PASSWORD,
            dbname=catalogos.PG_DATABASE,
        )
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'onms'
                  AND table_name = 'inventario_hlx'
                ORDER BY ordinal_position
            """)
            cols = [r[0] for r in cur.fetchall()]
            if cols:
                for c in cols:
                    print(f"      - {c}")
            else:
                print("      (sin columnas: revisar nombre de tabla/schema)")
        conn.close()
    except Exception as e:
        print(f"      ERROR consultando information_schema: {e}")

    # 3. Conteo de filas con ese CI (para confirmar que el dato existe)
    print(f"\n[3] Filas en inventario_hlx con CINUM = '{CI_PRUEBA}':")
    try:
        conn = psycopg2.connect(
            host=catalogos.PG_HOST, port=catalogos.PG_PORT,
            user=catalogos.PG_USER, password=catalogos.PG_PASSWORD,
            dbname=catalogos.PG_DATABASE,
        )
        with conn.cursor() as cur:
            cur.execute(
                'SELECT count(*) FROM onms.inventario_hlx WHERE "CINUM" = %s',
                (CI_PRUEBA,)
            )
            n = cur.fetchone()[0]
            print(f"      {n} fila(s)")
        conn.close()
    except Exception as e:
        print(f"      ERROR: {e}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
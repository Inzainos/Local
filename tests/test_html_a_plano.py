"""El reenvío SIN FORMATO mostraba los <b></b> crudos (36 veces, 10→17 oct 2026).

La defensa del 8-oct reenviaba el MISMO texto HTML sin parse_mode para no
perder el aviso — pero «sin formato» tenía que ser texto plano DE VERDAD.
"""


def test_html_a_plano_quita_las_etiquetas_y_devuelve_las_entidades():
    from telegram_bot import _html_a_plano

    m = "<b>REPORTE</b>\n<i>06:00</i>\nKp 1,6 & Bz < -5\n<a href='x'>mini</a>"
    out = _html_a_plano(m)
    assert "<b>" not in out and "</b>" not in out
    assert "<i>" not in out and "</a>" not in out
    assert "Kp 1,6 & Bz < -5" in out
    assert "REPORTE" in out and "06:00" in out and "mini" in out


def test_html_a_plano_con_texto_vacio_o_limpio_no_rompe():
    from telegram_bot import _html_a_plano

    assert _html_a_plano("") == ""
    assert _html_a_plano("ya soy plano") == "ya soy plano"

"""Contrato del cliente de IA; no realiza llamadas ni consume saldo."""
import os
import types
import unittest
from unittest.mock import patch

from test_registro import cargar_modulos, datos_validos


def respuesta(contenido, fin="stop"):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(
        finish_reason=fin, message=types.SimpleNamespace(content=contenido))])


class DeepSeek(unittest.TestCase):
    def modulo(self, **variables):
        config = {"IA_PROVEEDOR": "deepseek", "DEEPSEEK_API_KEY": "prueba", "GROQ_API_KEY": ""}
        config.update(variables)
        with patch.dict(os.environ, config):
            return cargar_modulos()[0]

    def test_usa_clave_deepseek_sin_necesitar_groq(self):
        modulo = self.modulo()
        self.assertEqual(modulo.IA_PROVEEDOR, "deepseek")
        self.assertEqual(modulo.MODELO_VISION["model"], "deepseek-flash")
        self.assertEqual(modulo.MODELO_TEXTO["model"], "deepseek-flash")
        self.assertEqual(self.modulo(DEEPSEEK_MODELO_TEXTO=" otro ").MODELO_TEXTO["model"], "otro")

    def test_proveedor_y_clave_invalidos_fallan_al_iniciar(self):
        for variables, error in (({"IA_PROVEEDOR": "otro"}, "IA_PROVEEDOR"),
                                 ({"DEEPSEEK_API_KEY": ""}, "DEEPSEEK_API_KEY")):
            with self.subTest(variables=variables), self.assertRaisesRegex(ValueError, error):
                self.modulo(**variables)

    def test_pipeline_dos_pasos_no_envia_opciones_groq_a_deepseek(self):
        import json
        modulo = self.modulo(GROQ_VISION_EXTRA_PARAMS="no se usa")
        crear = modulo.llm_client.chat.completions.create
        crear.side_effect = [respuesta("Texto del comprobante de prueba"), respuesta(json.dumps(datos_validos()))]
        self.assertEqual(modulo.extraer_datos_recibo_llm(b"imagen", "Materiales"), datos_validos())
        self.assertEqual(crear.call_count, 2)
        for llamada in crear.call_args_list:
            self.assertNotIn("max_completion_tokens", llamada.kwargs)
            self.assertNotIn("reasoning_effort", llamada.kwargs)
            self.assertEqual(llamada.kwargs["extra_body"], {"thinking": {"type": "disabled"}})
        self.assertEqual(crear.call_args_list[0].kwargs["max_tokens"], 2048)
        self.assertEqual(crear.call_args_list[1].kwargs["max_tokens"], 512)
        self.assertEqual(crear.call_args.kwargs["response_format"], {"type": "json_object"})

    def test_respuesta_incompleta_no_produce_datos(self):
        modulo = self.modulo()
        for contenido, fin in (("recibo incompleto", "length"), (None, "stop"), ("", "stop")):
            with self.subTest(contenido=contenido), self.assertRaises(ValueError):
                modulo._contenido_llm(respuesta(contenido, fin))

    def test_saldo_insuficiente_tiene_mensaje_especifico(self):
        self.assertIn("no tiene saldo", self.modulo()._identificar_error_llm(Exception("402 Insufficient Balance")))


if __name__ == "__main__":
    unittest.main()

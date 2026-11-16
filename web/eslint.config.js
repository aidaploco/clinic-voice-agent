import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  reactHooks.configs.flat.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
    rules: {
      // The page shows what a caller said; a rule against innerHTML is a rule against injection.
      "no-restricted-properties": ["error",
        { property: "innerHTML", message: "Text from a call must never be written as markup." },
        { property: "insertAdjacentHTML", message: "Text from a call must never be written as markup." },
      ],
    },
  },
);

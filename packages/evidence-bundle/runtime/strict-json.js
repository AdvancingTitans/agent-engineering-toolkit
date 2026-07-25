import { EvidenceBundleError } from "./types.js";
export function parseStrictJson(text, label) {
    const parser = new StrictJsonParser(text, label);
    return parser.parse();
}
class StrictJsonParser {
    #text;
    #label;
    #position = 0;
    constructor(text, label){
        this.#text = text;
        this.#label = label;
    }
    parse() {
        const value = this.#value();
        this.#whitespace();
        if (this.#position !== this.#text.length) {
            this.#fail("contains trailing content");
        }
        return value;
    }
    #value() {
        this.#whitespace();
        const character = this.#text[this.#position];
        if (character === "{") {
            return this.#object();
        }
        if (character === "[") {
            return this.#array();
        }
        if (character === '"') {
            return this.#string();
        }
        if (character === "t") {
            return this.#literal("true", true);
        }
        if (character === "f") {
            return this.#literal("false", false);
        }
        if (character === "n") {
            return this.#literal("null", null);
        }
        return this.#number();
    }
    #object() {
        this.#position += 1;
        const result = {};
        const keys = new Set();
        this.#whitespace();
        if (this.#text[this.#position] === "}") {
            this.#position += 1;
            return result;
        }
        while(true){
            this.#whitespace();
            if (this.#text[this.#position] !== '"') {
                this.#fail("requires a quoted object key");
            }
            const key = this.#string();
            if (keys.has(key)) {
                this.#fail(`contains duplicate object key ${JSON.stringify(key)}`);
            }
            keys.add(key);
            this.#whitespace();
            this.#expect(":");
            result[key] = this.#value();
            this.#whitespace();
            const separator = this.#text[this.#position];
            if (separator === "}") {
                this.#position += 1;
                return result;
            }
            this.#expect(",");
        }
    }
    #array() {
        this.#position += 1;
        const result = [];
        this.#whitespace();
        if (this.#text[this.#position] === "]") {
            this.#position += 1;
            return result;
        }
        while(true){
            result.push(this.#value());
            this.#whitespace();
            const separator = this.#text[this.#position];
            if (separator === "]") {
                this.#position += 1;
                return result;
            }
            this.#expect(",");
        }
    }
    #string() {
        const start = this.#position;
        this.#position += 1;
        let escaped = false;
        while(this.#position < this.#text.length){
            const character = this.#text[this.#position];
            this.#position += 1;
            if (escaped) {
                escaped = false;
            } else if (character === "\\") {
                escaped = true;
            } else if (character === '"') {
                const encoded = this.#text.slice(start, this.#position);
                try {
                    return JSON.parse(encoded);
                } catch  {
                    this.#fail("contains an invalid JSON string");
                }
            } else if (character.charCodeAt(0) < 0x20) {
                this.#fail("contains an unescaped control character");
            }
        }
        this.#fail("contains an unterminated JSON string");
    }
    #number() {
        const remainder = this.#text.slice(this.#position);
        const match = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/u.exec(remainder);
        if (match === null) {
            this.#fail("contains an invalid JSON value");
        }
        this.#position += match[0].length;
        const value = Number(match[0]);
        if (!Number.isFinite(value)) {
            this.#fail("contains a non-finite number");
        }
        return value;
    }
    #literal(encoded, value) {
        if (!this.#text.startsWith(encoded, this.#position)) {
            this.#fail("contains an invalid JSON literal");
        }
        this.#position += encoded.length;
        return value;
    }
    #expect(character) {
        if (this.#text[this.#position] !== character) {
            this.#fail(`expected ${JSON.stringify(character)}`);
        }
        this.#position += 1;
    }
    #whitespace() {
        while(/[\t\n\r ]/u.test(this.#text[this.#position] ?? "")){
            this.#position += 1;
        }
    }
    #fail(message) {
        throw new EvidenceBundleError("invalid_json", `${this.#label} ${message} at offset ${this.#position}`);
    }
}

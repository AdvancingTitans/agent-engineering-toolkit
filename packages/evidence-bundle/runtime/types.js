export class EvidenceBundleError extends Error {
    code;
    constructor(code, message){
        super(message);
        this.name = "EvidenceBundleError";
        this.code = code;
    }
}

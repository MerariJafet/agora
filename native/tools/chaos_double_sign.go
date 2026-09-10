// TEST-only offline evidence; ephemeral in-memory key; public output only.
package main
import (
 "bytes"
 "encoding/json"
 "fmt"
 "os"
 "time"
 "github.com/cometbft/cometbft/crypto/ed25519"
 cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
 "github.com/cometbft/cometbft/types"
)
func main() {
 key:=ed25519.GenPrivKey(); clone:=append(ed25519.PrivKey{},key...); pub:=key.PubKey()
 chainID:="tokoin-test-double-sign-offline"; stamp:=time.Unix(1700000000,0).UTC()
 votes:=make([]*types.Vote,2)
 for i:=range votes {
  votes[i]= &types.Vote{Type:cmtproto.PrecommitType,Height:10,Round:0,
   BlockID:types.BlockID{Hash:bytes.Repeat([]byte{byte(i+1)},32),PartSetHeader:types.PartSetHeader{Total:1,Hash:bytes.Repeat([]byte{byte(i+3)},32)}},
   Timestamp:stamp,ValidatorAddress:pub.Address(),ValidatorIndex:0}
  signer:=key; if i==1 {signer=clone}
  signature,err:=signer.Sign(types.VoteSignBytes(chainID,votes[i].ToProto()));if err!=nil {panic(err)}
  votes[i].Signature=signature
  if !pub.VerifySignature(types.VoteSignBytes(chainID,votes[i].ToProto()),signature) {panic("signature")}
 }
 evidence,err:=types.NewDuplicateVoteEvidence(votes[0],votes[1],stamp,types.NewValidatorSet([]*types.Validator{types.NewValidator(pub,10)}))
 if err!=nil {panic(err)};if err=evidence.ValidateBasic();err!=nil {panic(err)}
 if votes[0].BlockID.Equals(votes[1].BlockID) {panic("votes must conflict")}
 output:=map[string]any{"mode":"TEST_NON_RECOGNIZABLE","status":"PASS_OFFLINE_CHARACTERIZATION",
 "network_evidence_broadcast":false,"chain_id":chainID,"public_key":pub.Bytes(),
 "same_height_round_type_signer":true,"distinct_blocks":true,"both_signatures_verified":true,
 "comet_evidence_validate_basic":true,"evidence_hash":fmt.Sprintf("%X",evidence.Hash()),"evidence":evidence,
 "interpretation":"Valid canonical duplicate-vote evidence; does not test network detection or punishment"}
 if err=json.NewEncoder(os.Stdout).Encode(output);err!=nil {panic(err)}
}

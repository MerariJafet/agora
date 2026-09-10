// Genuine duplicate-vote evidence for a running ephemeral TEST network.
package main
import (
 "bytes"
 "encoding/json"
 "flag"
 "fmt"
 "os"
 "strings"
 cmtjson "github.com/cometbft/cometbft/libs/json"
 "github.com/cometbft/cometbft/privval"
 cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
 rpctypes "github.com/cometbft/cometbft/rpc/core/types"
 "github.com/cometbft/cometbft/types"
)
func main(){
 commitPath:=flag.String("commit","","public RPC result");genesisPath:=flag.String("genesis","","public TEST genesis")
 keyPath:=flag.String("key","","ephemeral TEST key");statePath:=flag.String("state","","ephemeral state");flag.Parse()
 if !strings.Contains(*keyPath,"agora-chaos-TEST-"){panic("ephemeral TEST key required")}
 genesis,err:=types.GenesisDocFromFile(*genesisPath);if err!=nil{panic(err)}
 if !strings.HasPrefix(genesis.ChainID,"tokoin-test-"){panic("TEST chain required")}
 raw,err:=os.ReadFile(*commitPath);if err!=nil{panic(err)}
 var response rpctypes.ResultCommit;if err=cmtjson.Unmarshal(raw,&response);err!=nil{panic(err)}
 pv:=privval.LoadFilePV(*keyPath,*statePath);pub:=pv.Key.PubKey
 var vote *types.Vote
 for i,sig:=range response.SignedHeader.Commit.Signatures{
  if sig.BlockIDFlag==types.BlockIDFlagCommit && bytes.Equal(sig.ValidatorAddress,pub.Address()){
   vote=&types.Vote{Type:cmtproto.PrecommitType,Height:response.SignedHeader.Commit.Height,Round:response.SignedHeader.Commit.Round,
    BlockID:response.SignedHeader.Commit.BlockID,Timestamp:sig.Timestamp,ValidatorAddress:pub.Address(),ValidatorIndex:int32(i),Signature:sig.Signature}
  }
 }
 if vote==nil{panic("selected validator absent from commit")}
 if !pub.VerifySignature(types.VoteSignBytes(genesis.ChainID,vote.ToProto()),vote.Signature){panic("canonical signature invalid")}
 fake:=vote.Copy();fake.BlockID.Hash=bytes.Repeat([]byte{99},32)
 fake.Signature,err=pv.Key.PrivKey.Sign(types.VoteSignBytes(genesis.ChainID,fake.ToProto()));if err!=nil{panic(err)}
 if !pub.VerifySignature(types.VoteSignBytes(genesis.ChainID,fake.ToProto()),fake.Signature){panic("conflicting signature invalid")}
 vals:=make([]*types.Validator,0);for _,v:=range genesis.Validators{vals=append(vals,types.NewValidator(v.PubKey,v.Power))}
 evidence,err:=types.NewDuplicateVoteEvidence(vote,fake,response.SignedHeader.Header.Time,types.NewValidatorSet(vals));if err!=nil{panic(err)}
 if err=evidence.ValidateBasic();err!=nil{panic(err)}
 payload,err:=cmtjson.Marshal(evidence);if err!=nil{panic(err)}
 json.NewEncoder(os.Stdout).Encode(map[string]any{"mode":"TEST_NON_RECOGNIZABLE","chain_id":genesis.ChainID,
  "evidence":json.RawMessage(payload),"evidence_hash":fmt.Sprintf("%X",evidence.Hash()),"both_signatures_verified":true,
  "height":vote.Height,"validator":fmt.Sprintf("%X",pub.Address())})
}

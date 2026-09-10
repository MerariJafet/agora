// Explicit TEST remote signer fault injector, using official CometBFT APIs.
// This changes requested vote timestamps, NOT the process/host clock.
package main
import (
 "encoding/json"
 "flag"
 "net"
 "os"
 "strings"
 "time"
 "github.com/cometbft/cometbft/crypto/ed25519"
 "github.com/cometbft/cometbft/libs/log"
 cmtos "github.com/cometbft/cometbft/libs/os"
 "github.com/cometbft/cometbft/privval"
 pvproto "github.com/cometbft/cometbft/proto/tendermint/privval"
 "github.com/cometbft/cometbft/types"
)
type faults struct { SkewSeconds int `json:"skew_seconds"`; DelayMs int `json:"delay_ms"`; FailProposal bool `json:"fail_proposal"` }
func main() {
 addr:=flag.String("addr","","loopback remote signer endpoint")
 chain:=flag.String("chain-id","","TEST chain")
 key:=flag.String("key","","ephemeral TEST key path")
 state:=flag.String("state","","ephemeral signing state")
 control:=flag.String("control","","fault control JSON")
 flag.Parse()
 host,_,err:=net.SplitHostPort(*addr)
 if err!=nil || host!="127.0.0.1" || !strings.HasPrefix(*chain,"tokoin-test-") || !strings.Contains(*key,"agora-chaos-TEST-") {panic("TEST/loopback guard")}
 logger:=log.NewTMLogger(log.NewSyncWriter(os.Stderr))
 pv:=privval.LoadFilePV(*key,*state)
 endpoint:=privval.NewSignerDialerEndpoint(logger,privval.DialTCPFn(*addr,3*time.Second,ed25519.GenPrivKey()),privval.SignerDialerEndpointConnRetries(1000))
 server:=privval.NewSignerServer(endpoint,*chain,pv)
 server.SetRequestHandler(func(p types.PrivValidator, req pvproto.Message, chainID string)(pvproto.Message,error){
  var f faults
  data,e:=os.ReadFile(*control);if e!=nil {panic(e)};if e=json.Unmarshal(data,&f);e!=nil {panic(e)}
  if f.SkewSeconds>3600 || f.SkewSeconds< -3600 || f.DelayMs<0 || f.DelayMs>5000 {panic("fault bounds")}
  switch r:=req.Sum.(type) {
  case *pvproto.Message_SignVoteRequest:
   if f.DelayMs>0 {time.Sleep(time.Duration(f.DelayMs)*time.Millisecond)}
   r.SignVoteRequest.Vote.Timestamp=r.SignVoteRequest.Vote.Timestamp.Add(time.Duration(f.SkewSeconds)*time.Second)
   json.NewEncoder(os.Stdout).Encode(map[string]any{"event":"vote","height":r.SignVoteRequest.Vote.Height,"round":r.SignVoteRequest.Vote.Round,"skew_seconds":f.SkewSeconds,"delay_ms":f.DelayMs})
  case *pvproto.Message_SignProposalRequest:
   if f.FailProposal {
    json.NewEncoder(os.Stdout).Encode(map[string]any{"event":"proposal_refused","height":r.SignProposalRequest.Proposal.Height,"round":r.SignProposalRequest.Proposal.Round})
    return pvproto.Message{Sum:&pvproto.Message_SignedProposalResponse{SignedProposalResponse:&pvproto.SignedProposalResponse{Error:&pvproto.RemoteSignerError{Code:1,Description:"TEST injected proposal refusal"}}}},nil
   }
  }
  return privval.DefaultValidationRequestHandler(p,req,chainID)
 })
 if err=server.Start();err!=nil {panic(err)}
 cmtos.TrapSignal(logger,func(){server.Stop()})
 select{}
}

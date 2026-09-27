package ojson

import "testing"

func TestRoundTripKeepsOrderAndNumbers(t *testing.T) {
	in := "{\n  \"zeta\": 1,\n  \"alpha\": {\n    \"b\": 1.50,\n    \"a\": [\n      true,\n      null,\n      \"x<y&z\"\n    ]\n  },\n  \"empty\": {},\n  \"list\": [],\n  \"big\": 12345678901234567890\n}\n"
	v, err := Decode([]byte(in))
	if err != nil {
		t.Fatal(err)
	}
	out, err := Encode(v)
	if err != nil {
		t.Fatal(err)
	}
	if string(out) != in {
		t.Fatalf("round trip changed the document:\n got %q\nwant %q", out, in)
	}
}

func TestSetKeepsPositionAndDeleteRemoves(t *testing.T) {
	o := NewObject()
	o.Set("a", 1)
	o.Set("b", 2)
	o.Set("a", 3)
	if got := o.Keys(); len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Fatalf("keys = %v", got)
	}
	if v := o.SetDefault("a", 9); v != 3 {
		t.Fatalf("SetDefault overwrote: %v", v)
	}
	o.Delete("a")
	if o.Has("a") || len(o.Keys()) != 1 {
		t.Fatalf("delete failed: %v", o.Keys())
	}
}

func TestDecodeRejectsTrailingData(t *testing.T) {
	if _, err := Decode([]byte(`{} {}`)); err == nil {
		t.Fatal("expected an error for trailing data")
	}
}

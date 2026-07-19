import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { login } from "./actions";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const params = await searchParams;
  const next = params.next ?? "/";

  return (
    <div className="flex flex-1 items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-base">請輸入密碼</CardTitle>
        </CardHeader>
        <CardContent>
          <form action={login} className="space-y-3">
            <input type="hidden" name="next" value={next} />
            <Input type="password" name="password" placeholder="密碼" autoFocus required />
            {params.error && <p className="text-sm text-destructive">密碼錯誤，請再試一次。</p>}
            <Button type="submit" className="w-full">
              登入
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

import java.util.HashMap;
import java.util.Stack;

//class ResourceUnavailableException extends RuntimeException
//{
//    public ResourceUnavailableException(String message)
//    {
//        super(message);
//    }
//}


class Parser
{
 private HashMap pairs = new HashMap();
 pairs.put("{", "}");
 pairs.put("(", ")");
 
 static boolean checkParenthesis(String s)
 {
  Stack st = new Stack();
  for (char c : s)
  {
   if (st.empty())
   {
    st.push(c);
    continue;
   }
   char p = (char) st.peek();
   char m = (char) pairs.get(p);
   if (c == m)
   {
    st.pop();
   }
   else
   {
    st.push(c):
   }
  }
  if (st.empty())
  {
   return true;
  }
  return false;
 }
}

class Solution

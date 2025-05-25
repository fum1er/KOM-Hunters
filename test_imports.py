#!/usr/bin/env python3
"""
Test script to verify all imports work correctly before deployment
"""

def test_imports():
    """Test all critical imports for the KOM Hunters app"""
    print("Testing imports...")
    
    try:
        # Test basic dependencies
        import dash
        print("✅ dash imported successfully")
        
        import plotly
        print("✅ plotly imported successfully")
        
        import requests
        print("✅ requests imported successfully")
        
        import polyline
        print("✅ polyline imported successfully")
        
        import geopy
        print("✅ geopy imported successfully")
        
        # Test langchain dependencies
        import langchain
        print("✅ langchain imported successfully")
        
        from langchain_openai import ChatOpenAI
        print("✅ langchain_openai.ChatOpenAI imported successfully")
        
        from langchain.prompts import ChatPromptTemplate
        print("✅ langchain.prompts.ChatPromptTemplate imported successfully")
        
        from langchain_core.output_parsers import StrOutputParser
        print("✅ langchain_core.output_parsers.StrOutputParser imported successfully")
        
        # Test strava_analyzer import
        import strava_analyzer
        print("✅ strava_analyzer imported successfully")
        
        print("\n🎉 All imports successful! Ready for deployment.")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_imports()
    if not success:
        print("\n⚠️ Some imports failed. Check your requirements.txt and dependencies.")
        exit(1)
    else:
        print("\n✅ All tests passed!")
